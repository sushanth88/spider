import os
import time
from typing import List, Dict, Optional
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProductScraper:
    """Handles web scraping of product prices using Playwright."""

    def __init__(self, username: str, password: str, headless: bool = True, search_query: str = "spirits",
                 enable_infinite_scroll: bool = False, scroll_pause_time: float = 2.0,
                 scroll_max_attempts: int = 100, scroll_no_new_products_threshold: int = 3, database=None):
        """
        Initialize the scraper.

        Args:
            username: Login username
            password: Login password
            headless: Run browser in headless mode
            search_query: Product search query (default: "spirits")
            enable_infinite_scroll: Enable infinite scroll to collect all products (default: False)
            scroll_pause_time: Seconds to wait after each scroll for content to load (default: 2.0)
            scroll_max_attempts: Maximum scroll attempts as safety limit (default: 100)
            scroll_no_new_products_threshold: Stop after N scrolls with no new products (default: 3)
            database: Database instance for real-time insertion (optional)
        """
        self.username = username
        self.password = password
        self.headless = headless
        self.search_query = search_query
        self.database = database

        # Use search URL with query parameter
        if search_query.lower() in ['', 'browse']:
            # Browse all products category page
            self.target_url = "https://now.breakthrubev.com/bbg/en/Shop-All/Spirits"
        elif search_query.lower() == 'all':
            # Search for all products (supports infinite scroll)
            self.target_url = "https://now.breakthrubev.com/bbg/en/search/?q=all"
        else:
            # Specific search query
            self.target_url = f"https://now.breakthrubev.com/bbg/en/search?text={search_query}"

        self.login_url = os.getenv('LOGIN_URL', "https://www.breakthrubev.com/login")
        self.base_domain = "https://now.breakthrubev.com"

        # Infinite scroll configuration
        self.enable_infinite_scroll = enable_infinite_scroll
        self.scroll_pause_time = scroll_pause_time
        self.scroll_max_attempts = scroll_max_attempts
        self.scroll_no_new_products_threshold = scroll_no_new_products_threshold

    def scrape_products(self, max_retries: int = 3) -> List[Dict]:
        """
        Scrape products with retry logic.

        Args:
            max_retries: Maximum number of retry attempts

        Returns:
            List of scraped products

        Raises:
            Exception: If scraping fails after all retries
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Scraping attempt {attempt + 1}/{max_retries}")
                return self._scrape_with_playwright()
            except Exception as e:
                logger.error(f"Scraping attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(5 * (attempt + 1))

    def _scrape_with_playwright(self) -> List[Dict]:
        """
        Perform the actual scraping using Playwright.

        Returns:
            List of scraped products
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()

            try:
                # Login
                logger.info("Attempting to log in...")
                self._login(page)

                # Navigate to search results
                logger.info(f"Navigating to target page: {self.target_url}")
                page.goto(self.target_url, wait_until="networkidle", timeout=30000)
                time.sleep(2)

                # Extract products
                logger.info("Extracting product data...")
                products = self._extract_products(page)
                logger.info(f"Successfully extracted {len(products)} products")

                return products

            finally:
                browser.close()

    def _login(self, page: Page):
        """
        Handle the login flow.

        Args:
            page: Playwright page object

        Raises:
            Exception: If login fails
        """
        try:
            # Use "load" wait strategy with extended timeout for slow page loads
            try:
                page.goto(self.login_url, wait_until="load", timeout=60000)
            except Exception as e:
                logger.warning(f"Page load timed out or failed: {e}. Continuing anyway...")
            time.sleep(3)  # Wait for any dynamic content to load

            # Wait for page to fully load
            time.sleep(2)

            # Accept cookie notice if present (new location)
            try:
                # Try multiple cookie button selectors
                cookie_selectors = [
                    'button:has-text("Accept")',
                    'button.js-cookie-banner-btn',
                    'button[class*="cookie"]',
                    'a:has-text("Accept")'
                ]
                for selector in cookie_selectors:
                    try:
                        cookie_btn = page.wait_for_selector(selector, timeout=2000, state='visible')
                        if cookie_btn and cookie_btn.is_visible():
                            cookie_btn.click()
                            logger.info(f"Accepted cookie notice with selector: {selector}")
                            time.sleep(1)
                            break
                    except:
                        continue
            except:
                logger.info("No cookie notice found or already accepted")

            # Wait for login form modal to appear
            time.sleep(2)

            # Look for login form selectors
            # Based on screenshot: Email * and Password * fields in a modal
            username_selectors = [
                'input[placeholder="Email *"]',
                'input[placeholder*="Email"]',
                'input[type="email"]',
                'input[name="email"]',
                'input[name="username"]',
                'input.gigya-input-text[name="username"]',
                'input[id*="email"]',
                'input[id*="username"]',
                '#email',
                '#username'
            ]

            password_selectors = [
                'input[placeholder="Password *"]',
                'input[placeholder*="Password"]',
                'input[type="password"]',
                'input[name="password"]',
                'input.gigya-input-password[name="password"]',
                '#password'
            ]

            submit_selectors = [
                'button:has-text("Log In")',
                'button:has-text("Log in")',
                'button:has-text("LOGIN")',
                'button[type="submit"]',
                'input[type="submit"]',
                'input.gigya-input-submit[type="submit"]',
                'button:has-text("Sign in")'
            ]

            # Debug: Log all inputs on the page
            logger.info("Scanning page for input fields...")
            all_inputs = page.query_selector_all('input')
            logger.info(f"Found {len(all_inputs)} input fields total")
            for i, inp in enumerate(all_inputs[:10]):  # Log first 10
                try:
                    inp_type = inp.get_attribute('type') or 'text'
                    inp_placeholder = inp.get_attribute('placeholder') or ''
                    inp_visible = inp.is_visible()
                    logger.info(f"  Input {i+1}: type={inp_type}, placeholder={inp_placeholder}, visible={inp_visible}")
                except:
                    pass

            # Find and fill username field (only visible fields)
            username_field = None
            for selector in username_selectors:
                try:
                    username_field = page.wait_for_selector(selector, state='visible', timeout=5000)
                    if username_field and username_field.is_visible():
                        logger.info(f"Found username field with selector: {selector}")
                        break
                except:
                    continue

            if not username_field:
                logger.error(f"Could not find username field. Tried selectors: {username_selectors[:5]}")
                raise Exception("Could not find username field")

            username_field.fill(self.username)
            time.sleep(1)

            # Find and fill password field (only visible fields)
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = page.wait_for_selector(selector, state='visible', timeout=5000)
                    if password_field and password_field.is_visible():
                        logger.info(f"Found password field with selector: {selector}")
                        break
                except:
                    continue

            if not password_field:
                raise Exception("Could not find password field")

            password_field.fill(self.password)
            # Wait for form to update/enable submit button
            time.sleep(2)

            # Find and click submit button - the "Log in" button is an input element
            submit_clicked = False

            # Try to click the visible Gigya submit button (it's an input, not a button)
            try:
                # Find all submit inputs and click the visible one
                submit_inputs = page.query_selector_all('input.gigya-input-submit[type="submit"]')
                for submit_input in submit_inputs:
                    if submit_input.is_visible():
                        logger.info("Found visible Gigya submit button, clicking...")
                        submit_input.click(force=True)
                        submit_clicked = True
                        break
            except Exception as e:
                logger.warning(f"Failed to click Gigya submit: {e}")

            # Fallback: try other selectors
            if not submit_clicked:
                for selector in submit_selectors:
                    try:
                        submit_button = page.wait_for_selector(selector, state='visible', timeout=3000)
                        if submit_button and submit_button.is_visible():
                            logger.info(f"Found submit button with selector: {selector}")
                            submit_button.click(force=True)
                            submit_clicked = True
                            break
                    except:
                        continue

            if not submit_clicked:
                raise Exception("Could not click submit button")

            # Wait for navigation after login
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                # Sometimes networkidle doesn't trigger, wait for URL change instead
                time.sleep(3)

            logger.info("Login successful")

        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            # Take screenshot for debugging
            screenshot_path = "/app/screenshots/login_error.png"
            page.screenshot(path=screenshot_path)
            logger.info(f"Screenshot saved to {screenshot_path}")
            raise Exception(f"Login failed: {str(e)}")

    def _save_checkpoint(self, product_urls: List[str], checkpoint_file: str = "scroll_checkpoint.json"):
        """
        Save collected URLs to checkpoint file for resume capability.

        Args:
            product_urls: List of product URLs to save
            checkpoint_file: Path to checkpoint file
        """
        import json
        checkpoint_data = {
            'urls': product_urls,
            'timestamp': datetime.now().isoformat(),
            'total_urls': len(product_urls)
        }
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            logger.info(f"Checkpoint saved: {len(product_urls)} URLs saved to {checkpoint_file}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {str(e)}")

    def _load_checkpoint(self, checkpoint_file: str = "scroll_checkpoint.json") -> Optional[List[str]]:
        """
        Load URLs from checkpoint file if it exists.

        Args:
            checkpoint_file: Path to checkpoint file

        Returns:
            List of URLs if checkpoint exists, None otherwise
        """
        import json
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                logger.info(f"Checkpoint loaded: {len(data['urls'])} URLs from {data['timestamp']}")
                return data['urls']
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {str(e)}")
                return None
        return None

    def _navigate_with_retry(self, page: Page, url: str, max_retries: int = 3) -> bool:
        """
        Navigate to URL with retry logic for robustness.

        Args:
            page: Playwright page object
            url: URL to navigate to
            max_retries: Maximum number of retry attempts

        Returns:
            True if navigation succeeded, False otherwise
        """
        for attempt in range(max_retries):
            try:
                page.goto(url, wait_until="networkidle", timeout=15000)
                return True
            except PlaywrightTimeoutError:
                logger.warning(f"Navigation timeout (attempt {attempt+1}/{max_retries}): {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                else:
                    logger.error(f"Failed to navigate after {max_retries} attempts: {url}")
                    return False
            except Exception as e:
                logger.error(f"Navigation error (attempt {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return False
        return False

    def _collect_urls_via_pagination(self, page: Page) -> List[str]:
        """
        Navigate through all pagination pages to collect product URLs.

        Args:
            page: Playwright page object

        Returns:
            List of unique product URLs discovered
        """
        product_urls = set()
        current_page = 1
        max_pages = self.scroll_max_attempts  # Reuse as max pages to visit

        logger.info("Starting pagination to collect all product URLs...")

        while current_page <= max_pages:
            # Extract product URLs from current page
            product_cards = page.query_selector_all('.m-product-card')
            page_products = 0

            for card in product_cards:
                try:
                    link_elem = card.query_selector('a.m-product-card__link, a[href*="/p/"]')
                    if link_elem:
                        href = link_elem.get_attribute('href')
                        if href:
                            if href.startswith('/'):
                                url = f"{self.base_domain}{href}"
                            elif href.startswith('http'):
                                url = href
                            else:
                                continue
                            # Clean up query parameters
                            if '?' in url and '&ref=' in url:
                                url = url.split('&ref=')[0]
                            product_urls.add(url)
                            page_products += 1
                except Exception as e:
                    logger.debug(f"Error extracting URL from card: {str(e)}")
                    continue

            logger.info(f"Page {current_page}: Found {page_products} products on this page ({len(product_urls)} total unique)")

            # Check if we've found all products or reached a page with no products
            if page_products == 0:
                logger.info(f"No products found on page {current_page}, stopping pagination")
                break

            # Save checkpoint every 20 pages
            if current_page % 20 == 0:
                self._save_checkpoint(list(product_urls))
                logger.info(f"Progress: Visited {current_page} pages, collected {len(product_urls)} URLs")

            # Try to navigate to next page
            current_page += 1

            # Look for "next" button or page number link
            next_clicked = False

            # Strategy 1: Click the "next" arrow button
            next_selectors = [
                'a.m-pagination__link--next',
                'a[aria-label="Next"]',
                'a.pagination-next',
                'button.pagination-next',
                '.pagination .next'
            ]

            for selector in next_selectors:
                try:
                    next_button = page.query_selector(selector)
                    if next_button and next_button.is_visible():
                        logger.debug(f"Clicking next button: {selector}")
                        next_button.click()
                        next_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Failed to click next with selector {selector}: {e}")
                    continue

            # Strategy 2: Construct URL with page parameter
            if not next_clicked:
                try:
                    # Construct next page URL
                    base_url = page.url.split('?')[0]
                    query_params = page.url.split('?')[1] if '?' in page.url else 'q=all'

                    # Remove existing page parameter if present
                    params = [p for p in query_params.split('&') if not p.startswith('page=')]
                    params.append(f'page={current_page}')
                    next_url = f"{base_url}?{'&'.join(params)}"

                    logger.debug(f"Navigating to page {current_page}: {next_url}")
                    page.goto(next_url, wait_until="networkidle", timeout=15000)
                    next_clicked = True
                except Exception as e:
                    logger.error(f"Failed to navigate to page {current_page}: {e}")
                    break

            if not next_clicked:
                logger.warning(f"Could not navigate to page {current_page}, stopping pagination")
                break

            # Wait for page to load
            time.sleep(self.scroll_pause_time)

            try:
                page.wait_for_selector('.m-product-card', timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning(f"Products not loaded on page {current_page}")

        # Save final checkpoint
        self._save_checkpoint(list(product_urls))

        logger.info(f"Pagination complete: Visited {current_page - 1} pages, collected {len(product_urls)} unique product URLs")
        return list(product_urls)

    def _scroll_and_collect_product_urls(self, page: Page) -> List[str]:
        """
        Collect product URLs - uses pagination instead of scroll since the site uses pagination.

        Args:
            page: Playwright page object

        Returns:
            List of unique product URLs discovered
        """
        # Detect if pagination exists
        pagination = page.query_selector('.m-pagination, .pagination, nav[aria-label*="pagination" i]')

        if pagination:
            logger.info("Detected pagination controls - using pagination strategy")
            return self._collect_urls_via_pagination(page)
        else:
            logger.warning("No pagination detected - this may not collect all products")
            # Fallback to extracting visible products only
            product_urls = set()
            product_cards = page.query_selector_all('.m-product-card')
            for card in product_cards:
                try:
                    link_elem = card.query_selector('a.m-product-card__link, a[href*="/p/"]')
                    if link_elem:
                        href = link_elem.get_attribute('href')
                        if href:
                            if href.startswith('/'):
                                url = f"{self.base_domain}{href}"
                            elif href.startswith('http'):
                                url = href
                            else:
                                continue
                            product_urls.add(url)
                except Exception as e:
                    logger.debug(f"Error extracting URL: {e}")
            return list(product_urls)

    def _extract_products(self, page: Page) -> List[Dict]:
        """
        Extract product information from the search results page.

        Args:
            page: Playwright page object

        Returns:
            List of product dictionaries
        """
        products = []
        scraped_at = datetime.now()

        # Wait for product listings to load
        try:
            page.wait_for_selector('.m-product-card', timeout=10000)
            logger.info("Product cards loaded successfully")
        except PlaywrightTimeoutError:
            logger.warning("Product selector not found, attempting alternate selectors")

        # Collect product URLs
        product_urls = []

        if self.enable_infinite_scroll:
            # Use infinite scroll to collect all product URLs
            logger.info("Infinite scroll enabled - collecting all product URLs...")
            product_urls = self._scroll_and_collect_product_urls(page)
        else:
            # Original behavior: Extract from visible products only
            logger.info("Infinite scroll disabled - extracting from visible products only...")

            product_selectors = [
                '.m-product-card',
                'div[class*="product-card"]',
                '.product',
                '.product-item',
            ]

            # Try different selectors to find products
            product_elements = []
            for selector in product_selectors:
                product_elements = page.query_selector_all(selector)
                if product_elements:
                    logger.info(f"Found {len(product_elements)} products using selector: {selector}")
                    break

            if not product_elements:
                logger.warning("No products found with standard selectors")
                page.screenshot(path="no_products_found.png")
                return products

            # Extract URLs from visible elements
            for idx, element in enumerate(product_elements, 1):
                try:
                    basic_product = self._extract_product_from_element(element)
                    if basic_product and basic_product.get('url'):
                        product_urls.append(basic_product['url'])
                except Exception as e:
                    logger.error(f"Error extracting URL from product {idx}: {str(e)}")
                    continue

        logger.info(f"Found {len(product_urls)} product URLs, now fetching details...")

        # Second pass: Visit each product detail page to get full details
        for idx, url in enumerate(product_urls, 1):
            try:
                logger.info(f"[{idx}/{len(product_urls)}] Extracting details from: {url}")

                # Navigate to product page with retry logic
                if not self._navigate_with_retry(page, url):
                    logger.error(f"Skipping product {idx} - navigation failed")
                    continue
                time.sleep(1)

                # Extract product name and basic info from detail page
                product = {
                    'name': None,
                    'price': None,
                    'url': url,
                    'scraped_at': scraped_at
                }

                # Extract product name from detail page
                name_selectors = [
                    'h1.m-product-name',
                    'h1[data-product-name]',
                    '.m-product-overview__name',
                    'h1',
                ]
                for selector in name_selectors:
                    try:
                        name_elem = page.query_selector(selector)
                        if name_elem:
                            product['name'] = name_elem.inner_text().strip()
                            if product['name']:
                                break
                    except:
                        continue

                # Extract price from detail page
                price_selectors = [
                    '.m-product-card__price .a-price',
                    '.a-price',
                    '.price',
                    '[data-product-price]',
                ]
                for selector in price_selectors:
                    try:
                        price_elem = page.query_selector(selector)
                        if price_elem:
                            price_text = price_elem.inner_text().strip()
                            price = self._parse_price(price_text)
                            if price is not None:
                                product['price'] = price
                                break
                    except:
                        continue

                # Extract detailed product information
                detailed_product = self._extract_product_details(page, url)
                product.update(detailed_product)

                if product['name']:
                    products.append(product)
                    logger.info(f"[{idx}/{len(product_urls)}] Successfully extracted: {product['name']}")

                    # Insert to database immediately if database instance provided
                    if self.database:
                        try:
                            product_id = self.database.insert_product(
                                name=product['name'],
                                url=product.get('url'),
                                source='Breakthru Beverage',
                                product_id=product.get('product_id'),
                                bottle_upc=product.get('bottle_upc'),
                                case_upc=product.get('case_upc'),
                                size=product.get('size'),
                                qty_per_case=product.get('qty_per_case'),
                                proof_abv=product.get('proof_abv'),
                                container_type=product.get('container_type'),
                                brand=product.get('brand'),
                                supplier=product.get('supplier'),
                                country_of_origin=product.get('country_of_origin'),
                                region=product.get('region'),
                                categories=product.get('categories'),
                                product_details=product.get('product_details')
                            )

                            if product_id and product.get('price'):
                                self.database.insert_price(
                                    product_id=product_id,
                                    price=product['price'],
                                    scraped_at=product['scraped_at']
                                )

                            # Insert deals if present
                            if product_id and 'deals' in product and product['deals']:
                                self.database.delete_deals_for_product(product_id)
                                for deal in product['deals']:
                                    self.database.insert_deal(product_id, **deal)

                            logger.info(f"✅ Saved to database: {product['name']}")
                        except Exception as db_error:
                            logger.error(f"❌ Database insert failed for {product['name']}: {db_error}")
                else:
                    logger.warning(f"[{idx}/{len(product_urls)}] Could not extract name from: {url}")

            except Exception as e:
                logger.error(f"Error extracting product {idx} from {url}: {str(e)}")
                continue

            # Log progress every 50 products
            if idx % 50 == 0:
                logger.info(f"Progress: {idx}/{len(product_urls)} products processed ({(idx/len(product_urls)*100):.1f}%)")

        return products

    def _extract_product_from_element(self, element) -> Optional[Dict]:
        """
        Extract product data from a single element.

        Args:
            element: Playwright element locator

        Returns:
            Product dictionary or None if extraction fails
        """
        product = {
            'name': None,
            'price': None,
            'url': None
        }

        # Extract product name
        # New portal uses .m-product-card__name .a-product-name
        name_selectors = [
            '.m-product-card__name .a-product-name',
            '.m-product-card__name',
            '.a-product-name',
            '.product-name',
            '.product-title',
            'h2',
            'h3',
        ]

        for selector in name_selectors:
            try:
                name_elem = element.query_selector(selector)
                if name_elem:
                    product['name'] = name_elem.inner_text().strip()
                    if product['name']:
                        break
            except:
                continue

        # Extract price
        # New portal uses .m-product-card__price .a-price
        price_selectors = [
            '.m-product-card__price .a-price',
            '.a-price',
            '.m-product-card__price',
            '.price',
            '.product-price',
            '[class*="price"]',
        ]

        for selector in price_selectors:
            try:
                price_elem = element.query_selector(selector)
                if price_elem:
                    price_text = price_elem.inner_text().strip()
                    # Extract numeric value from price string
                    price = self._parse_price(price_text)
                    if price is not None:
                        product['price'] = price
                        break
            except:
                continue

        # Extract URL
        # New portal uses a.m-product-card__link
        try:
            link_elem = element.query_selector('a.m-product-card__link, a')
            if link_elem:
                href = link_elem.get_attribute('href')
                if href:
                    # Make absolute URL if relative
                    if href.startswith('/'):
                        product['url'] = f"{self.base_domain}{href}"
                    elif href.startswith('http'):
                        product['url'] = href
        except:
            pass

        # Only return if we have at least name
        if product['name']:
            if product['price'] is None:
                logger.warning(f"Product {product['name']} has no price, will extract details anyway")
            return product
        else:
            logger.warning(f"Product element missing name, URL: {product.get('url')}")
            return None

    def _parse_price(self, price_text: str) -> Optional[float]:
        """
        Parse price from text string.

        Args:
            price_text: Price as text (e.g., "$19.99", "£20.50")

        Returns:
            Price as float or None if parsing fails
        """
        try:
            # Remove currency symbols and whitespace
            cleaned = price_text.replace('$', '').replace('£', '').replace('€', '').replace(',', '').strip()

            # Extract first number (handles cases like "$19.99 USD")
            import re
            match = re.search(r'\d+\.?\d*', cleaned)
            if match:
                return float(match.group())

        except Exception as e:
            logger.error(f"Failed to parse price '{price_text}': {str(e)}")

        return None

    def _extract_product_details(self, page: Page, product_url: str) -> Dict:
        """
        Extract detailed product information from product detail page.

        Args:
            page: Playwright page object
            product_url: URL of the product detail page

        Returns:
            Dictionary with detailed product fields
        """
        details = {}

        try:
            # Navigate to product detail page
            page.goto(product_url, wait_until="networkidle", timeout=15000)
            time.sleep(1)

            # Extract brand from data attribute
            brand_elem = page.query_selector('[data-product-brand]')
            if brand_elem:
                details['brand'] = brand_elem.get_attribute('data-product-brand')

            # Extract supplier from data attribute
            supplier_elem = page.query_selector('[data-product-supplier]')
            if supplier_elem:
                details['supplier'] = supplier_elem.get_attribute('data-product-supplier')

            # Extract all description list items (contains most product details)
            desc_items = page.query_selector_all('.m-description-list__item')
            for item in desc_items:
                label_elem = item.query_selector('.m-description-list__item-label')
                data_elem = item.query_selector('.m-description-list__list-item-data')

                if label_elem and data_elem:
                    label = label_elem.inner_text().strip()
                    data = data_elem.inner_text().strip()

                    # Map labels to database fields
                    if label == 'Product ID':
                        details['product_id'] = data
                    elif label == 'Bottle UPC':
                        details['bottle_upc'] = data
                    elif label == 'Case UPC':
                        details['case_upc'] = data
                    elif label == 'Size':
                        details['size'] = data
                    elif label == 'QTY/CSE':
                        try:
                            details['qty_per_case'] = int(data)
                        except:
                            details['qty_per_case'] = data
                    elif label == 'Proof/ABV':
                        details['proof_abv'] = data
                    elif label == 'Container Type':
                        details['container_type'] = data
                    elif label == 'Brand':
                        details['brand'] = data
                    elif label == 'Supplier':
                        details['supplier'] = data
                    elif label == 'Country of Origin':
                        details['country_of_origin'] = data
                    elif label == 'Region':
                        details['region'] = data

            # Extract categories from URL path
            # URL format: /Shop-All/Spirits/Vodka/American-Vodka/Product-Name/p/12345
            current_url = page.url
            categories = []

            try:
                if '/Shop-All/' in current_url:
                    # Extract the path between Shop-All and /p/
                    parts = current_url.split('/Shop-All/')[1].split('/p/')[0]
                    # Split by / and decode URL encoding
                    import urllib.parse
                    category_parts = [urllib.parse.unquote(p) for p in parts.split('/') if p]

                    # Remove the last part (product name) - it's usually the most specific
                    if len(category_parts) > 1:
                        categories = category_parts[:-1]
                    else:
                        categories = category_parts
            except Exception as e:
                logger.debug(f"Could not extract categories from URL: {str(e)}")

            # Also try breadcrumbs as fallback
            if not categories:
                breadcrumbs = page.query_selector_all('.m-breadcrumbs__link, .breadcrumb a, nav[aria-label="breadcrumb"] a')
                for bc in breadcrumbs:
                    cat = bc.inner_text().strip()
                    if cat and cat not in ['Home', 'Shop All']:
                        categories.append(cat)

            if categories:
                details['categories'] = ', '.join(categories)

            # Extract QTY/CSE from product name if not already extracted
            # Look for patterns like "6B", "12B", "24B" (bottles per case)
            # or "6/12PK", "15/4PK" etc.
            if 'qty_per_case' not in details or not details['qty_per_case']:
                import re
                # Get product name from URL and page title
                product_name_from_url = page.url.split('/p/')[0].split('/')[-1] if '/p/' in page.url else ''
                product_name_from_title = page.title()

                # Try both sources
                for product_name in [product_name_from_url, product_name_from_title]:
                    if not product_name:
                        continue

                    # Pattern 1: "6B", "12B" etc (X bottles)
                    match = re.search(r'(\d+)B\b', product_name, re.IGNORECASE)
                    if match:
                        try:
                            qty = int(match.group(1))
                            details['qty_per_case'] = qty
                            logger.info(f"Extracted qty_per_case={qty} from product name pattern 'XB': {product_name[:50]}")
                            break
                        except:
                            pass

                    # Pattern 2: "12/10PK", "15/4PK" or "12-10PK" etc (X packs of Y)
                    match = re.search(r'(\d+)[/-](\d+)PK', product_name, re.IGNORECASE)
                    if match:
                        try:
                            qty = int(match.group(1)) * int(match.group(2))
                            details['qty_per_case'] = qty
                            logger.info(f"Extracted qty_per_case={qty} from product name pattern 'X/YPK': {product_name[:50]}")
                            break
                        except:
                            pass

            # Extract deals as structured data
            deals = self._extract_deals(page)
            if deals:
                details['deals'] = deals

            # Extract product description/details
            desc_section = page.query_selector('.m-product-overview__description')
            if desc_section:
                desc_text = desc_section.inner_text().strip()
                details['product_details'] = desc_text[:1000] if len(desc_text) > 1000 else desc_text

        except Exception as e:
            logger.error(f"Error extracting product details from {product_url}: {str(e)}")

        return details

    def _extract_deals(self, page: Page) -> List[Dict]:
        """
        Extract structured deal information from product page.

        Args:
            page: Playwright page object

        Returns:
            List of deal dictionaries with parsed fields
        """
        import json
        import re

        deals = []

        try:
            # Find all deal forms (they contain deal data as JSON in hidden inputs)
            deal_forms = page.query_selector_all('form[action*="/cart/add/deal"]')

            for form in deal_forms:
                try:
                    # Get the deal JSON from hidden input
                    deal_input = form.query_selector('input[name="deal"]')
                    if not deal_input:
                        continue

                    deal_json_str = deal_input.get_attribute('value')
                    if not deal_json_str:
                        continue

                    # Parse the JSON
                    deal_data = json.loads(deal_json_str)

                    # Determine action type (Add or Build button)
                    action_button = form.query_selector('button[type="submit"]')
                    action_type = None
                    if action_button:
                        button_text = action_button.inner_text().strip()
                        if 'Add' in button_text:
                            action_type = 'Add'
                        elif 'Build' in button_text:
                            action_type = 'Build'

                    # Parse price values (remove $ and convert to float)
                    def parse_price(price_str):
                        if not price_str:
                            return None
                        # Remove $ and commas, convert to float
                        cleaned = price_str.replace('$', '').replace(',', '').strip()
                        try:
                            return float(cleaned)
                        except:
                            return None

                    # Extract and map fields
                    deal = {
                        'deal_title': deal_data.get('dealDescription'),
                        'deal_number': deal_data.get('dealCode'),
                        'sku_number': deal_data.get('productId'),
                        'usage_limit': deal_data.get('useTimes'),
                        'quantity_type': 'Mix and Match' if deal_data.get('mixNMatch') else 'Exact Qty Only',
                        'bottle_fees_applicable': None,  # Not found in JSON
                        'quantity': deal_data.get('purchaseQty'),
                        'quantity_unit': deal_data.get('purchaseUom'),
                        'estimated_bottle_price': parse_price(deal_data.get('estBottlePrice')),
                        'cse_price': parse_price(deal_data.get('casePrice')),
                        'total_estimated_price': None,  # Calculate if needed
                        'total_cse_price': None,  # Calculate if needed
                        'action_type': action_type,
                        'discount_per_unit': deal_data.get('discount'),
                        'is_mix_and_match': 1 if deal_data.get('mixNMatch') else 0,
                        'deal_obj_type': deal_data.get('dealObj')
                    }

                    # Calculate totals if we have the data
                    if deal['quantity'] and deal['estimated_bottle_price']:
                        # Assuming quantity is in cases and we need to know bottles per case
                        # For now, just use the case price as total
                        deal['total_cse_price'] = deal['cse_price']

                    deals.append(deal)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse deal JSON: {str(e)}")
                    continue
                except Exception as e:
                    logger.warning(f"Error extracting deal: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting deals: {str(e)}")

        return deals
