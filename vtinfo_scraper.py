import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


logger = logging.getLogger(__name__)


VENDORS = {
    "nks": {"wholesaler_id": "00131", "name": "NKS Distributors"},
    "standard": {"wholesaler_id": "00128", "name": "Standard Distributing Company"},
}


class VTInfoScraper:
    """Scrape retailer-specific product catalogs from VTInfo."""

    def __init__(self, username=None, password=None, vendor="nks", retailer_id="15786",
                 headless=True, page_pause=0.25, database=None):
        if vendor not in VENDORS:
            raise ValueError(f"Unsupported vendor: {vendor}")

        self.username = username
        self.password = password
        self.vendor = vendor
        self.vendor_name = VENDORS[vendor]["name"]
        self.retailer_id = str(retailer_id)
        self.headless = headless
        self.page_pause = max(0, page_pause)
        self.database = database
        self.base_url = (
            f"https://apps.vtinfo.com/retailer-portal/"
            f"{VENDORS[vendor]['wholesaler_id']}/retailer/{self.retailer_id}"
        )
        self.catalog_url = f"{self.base_url}/search?sorter=description-asc&lastDelivered=all"

    def scrape_products(self, max_products=None):
        if sync_playwright is None:
            raise RuntimeError("Playwright is required; install dependencies from requirements.txt")

        products = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            page = browser.new_page()
            try:
                self._login(page)
                product_urls = self._collect_product_urls(page, max_products)
                logger.info("Collected %s product URLs for %s", len(product_urls), self.vendor_name)

                for index, product_url in enumerate(product_urls, start=1):
                    try:
                        product = self._extract_product(page, product_url)
                        if product:
                            products.append(product)
                            self._save_product(product)
                            logger.info("[%s/%s] Scraped %s", index, len(product_urls), product["name"])
                        if self.page_pause:
                            page.wait_for_timeout(int(self.page_pause * 1000))
                    except Exception:
                        logger.exception("Failed to scrape product: %s", product_url)
                return products
            finally:
                browser.close()

    def _login(self, page):
        page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=60000)
        if "login.vtinfo.com" not in page.url:
            page.get_by_role("link", name=re.compile(re.escape(self.vendor_name), re.I)).wait_for(timeout=30000)
            return

        if not self.username or not self.password:
            if self.headless:
                raise RuntimeError("Set VTINFO_USERNAME and VTINFO_PASSWORD, or run with --headed for manual sign-in")
            logger.info("Complete VTInfo sign-in in the visible browser; waiting for the portal redirect")
        else:
            email = page.locator('input[type="email"], input[placeholder*="example.com"]').first
            if email.count():
                email.fill(self.username)
                next_button = page.get_by_role("button", name=re.compile(r"^Next$", re.I))
                if next_button.count():
                    next_button.click()

            password = page.locator('input[type="password"]')
            password.wait_for(state="visible", timeout=30000)
            password.fill(self.password)
            page.get_by_role("button", name=re.compile(r"^Sign in$", re.I)).click()

        try:
            page.wait_for_url(
                re.compile(r"^https://apps\.vtinfo\.com/retailer-portal/"),
                timeout=300000 if not self.headless else 60000,
            )
        except PlaywrightTimeoutError as error:
            if self.headless:
                raise RuntimeError("VTInfo sign-in did not complete; check credentials or use --headed for MFA") from error
            raise RuntimeError("VTInfo sign-in did not complete within five minutes") from error

        page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=60000)

    def _collect_product_urls(self, page, max_products=None):
        page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('a[href*="/items/detail/"]', state="attached", timeout=30000)
        product_urls = []
        seen_urls = set()

        while True:
            hrefs = page.locator('a[href*="/items/detail/"]').evaluate_all(
                "anchors => anchors.map(anchor => anchor.getAttribute('href'))"
            )
            for href in hrefs:
                product_url = urljoin("https://apps.vtinfo.com", href or "")
                if product_url not in seen_urls:
                    seen_urls.add(product_url)
                    product_urls.append(product_url)
                    if max_products and len(product_urls) >= max_products:
                        return product_urls

            next_button = page.get_by_role("button", name="Next page").first
            if not next_button.count() or next_button.is_disabled():
                break

            first_href = hrefs[0] if hrefs else None
            next_button.click()
            if first_href:
                try:
                    page.wait_for_function(
                        "previous => { const link = document.querySelector('a[href*=\"/items/detail/\"]'); "
                        "return link && link.getAttribute('href') !== previous; }",
                        arg=first_href,
                        timeout=30000,
                    )
                except PlaywrightTimeoutError:
                    logger.warning("Catalog pagination did not advance; stopping after %s products", len(product_urls))
                    break

        return product_urls

    def _extract_product(self, page, product_url):
        page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
        page.get_by_role("button", name=re.compile("Add to Cart", re.I)).wait_for(timeout=30000)
        lines = [line.strip() for line in page.locator("body").inner_text().splitlines() if line.strip()]
        name = page.title().strip()
        if " | " in name:
            name = name.split(" | ", 1)[0].strip()

        item_id = urlparse(product_url).path.rstrip("/").split("/")[-1]
        try:
            item_index = lines.index(item_id)
        except ValueError:
            item_index = -1

        brand = lines[item_index - 2] if item_index >= 2 else None
        category = lines[item_index - 1] if item_index >= 1 else None
        package = ""
        package_selector = page.get_by_role("combobox")
        if package_selector.count():
            package = package_selector.first.inner_text().strip()

        price = self._extract_price(lines)
        abv = next((re.sub(r"^ABV:\s*", "", line, flags=re.I) for line in lines if line.lower().startswith("abv:")), None)
        description = self._extract_description(lines)
        case_upc = self._extract_upc(lines, "Case UPC")
        bottle_upc = self._extract_upc(lines, "Unit UPC") or self._extract_upc(lines, "Retail UPC")
        deals = self._extract_deals(page, item_id)
        quantity_match = re.search(r"[•·]\s*(\d+)", package)
        container_type = package.split(":", 1)[0].strip() if ":" in package else None

        return {
            "name": name,
            "url": product_url,
            "product_id": item_id,
            "price": price,
            "scraped_at": datetime.now(),
            "brand": brand,
            "categories": category,
            "size": package or None,
            "qty_per_case": int(quantity_match.group(1)) if quantity_match else None,
            "container_type": container_type,
            "proof_abv": abv,
            "bottle_upc": bottle_upc,
            "case_upc": case_upc,
            "source": self.vendor_name,
            "product_details": description,
            "deal_summary": deals[0]["deal_title"] if deals else None,
            "deals": deals,
        }

    def _extract_deals(self, page, item_id):
        view_deals = page.get_by_role("button", name=re.compile("View Deal", re.I))
        if not view_deals.count():
            return []

        try:
            view_deals.first.click()
            dialog = page.get_by_role("dialog")
            dialog.wait_for(state="visible", timeout=10000)
            dialog_text = dialog.inner_text()
            headings = [text.strip() for text in dialog.locator("h3").all_inner_texts() if text.strip()]
            deal_links = dialog.locator('a[href*="discountId"]').evaluate_all(
                "links => links.map(link => link.href)"
            )
            discount_ids = []
            for href in deal_links:
                discount_ids.extend(parse_qs(urlparse(href).query).get("discountId", []))

            return [
                self._parse_deal(title, item_id, discount_ids[index] if index < len(discount_ids) else None,
                                 "mix and match" in dialog_text.lower())
                for index, title in enumerate(headings)
            ]
        except PlaywrightTimeoutError:
            logger.warning("Deal dialog did not load for product %s", item_id)
            return None

    @staticmethod
    def _parse_deal(title, item_id, deal_number=None, is_mix_and_match=False):
        discount_match = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", title)
        quantity_match = re.search(
            r"(?:minimum order of|buy)\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)", title, re.I
        )
        return {
            "deal_title": title,
            "deal_number": deal_number,
            "sku_number": item_id,
            "quantity_type": "Mix and Match" if is_mix_and_match else "Exact Qty Only",
            "quantity": float(quantity_match.group(1)) if quantity_match else None,
            "quantity_unit": quantity_match.group(2) if quantity_match else None,
            "discount_per_unit": float(discount_match.group(1).replace(",", "")) if discount_match else None,
            "action_type": "Discount",
            "is_mix_and_match": int(is_mix_and_match),
        }

    @staticmethod
    def _extract_price(lines):
        for line in lines:
            if re.search(r"/\s*(?:Case|Unit|Keg)\b", line, re.I):
                match = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", line)
                if match:
                    return float(match.group(1).replace(",", ""))
        return None

    @staticmethod
    def _extract_upc(lines, label):
        labels = {"Case UPC", "Retail UPC", "Unit UPC"}
        for index, line in enumerate(lines):
            if line == label:
                digits = ""
                for value in lines[index + 1:]:
                    if value in labels:
                        break
                    digits += re.sub(r"\D", "", value)
                if 8 <= len(digits) <= 14:
                    return digits
        return None

    @staticmethod
    def _extract_description(lines):
        for index, line in enumerate(lines):
            if line.lower().startswith("nutrition facts") and index + 1 < len(lines):
                return lines[index + 1]
        return None

    def _save_product(self, product):
        if not self.database:
            return

        database_product_id = self.database.insert_product(
            name=product["name"],
            url=product["url"],
            product_id=product["product_id"],
            bottle_upc=product["bottle_upc"],
            case_upc=product["case_upc"],
            size=product["size"],
            qty_per_case=product["qty_per_case"],
            proof_abv=product["proof_abv"],
            container_type=product["container_type"],
            brand=product["brand"],
            source=product["source"],
            categories=product["categories"],
            deal_summary=product["deal_summary"],
            product_details=product["product_details"],
        )
        if database_product_id and product["price"] is not None:
            self.database.insert_price(database_product_id, product["price"], product["scraped_at"])
        if database_product_id and product["deals"] is not None:
            self.database.delete_deals_for_product(database_product_id)
            for deal in product["deals"]:
                self.database.insert_deal(database_product_id, **deal)