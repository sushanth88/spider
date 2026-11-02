import logging
from datetime import datetime

try:
    from shared_database import Database as SharedDatabase
except ImportError:
    from database import Database as SharedDatabase


logger = logging.getLogger(__name__)


class Database(SharedDatabase):
    """Store SGProof scrape results in the shared product, price, and deal tables."""

    def save_products(self, products):
        saved = 0
        for product in products:
            name = (product.get("name") or "").strip()
            if not name:
                continue

            try:
                shared_product_id = self.insert_product(
                    name=name,
                    url=product.get("url"),
                    product_id=product.get("product_id"),
                    size=product.get("size"),
                    qty_per_case=product.get("units_per_case"),
                    categories=product.get("deal_type"),
                    deal_summary=product.get("deal_type"),
                    product_details=product.get("deal_type"),
                    source="SGProof",
                )
                if not shared_product_id:
                    continue

                case_price = product.get("price_per_case")
                unit_price = product.get("price_per_unit")
                current_price = case_price if case_price is not None else unit_price
                if current_price is not None:
                    self.insert_price(
                        shared_product_id,
                        float(current_price),
                        scraped_at=datetime.now(),
                    )

                self.delete_deals_for_product(shared_product_id)
                has_deal = any(
                    product.get(key) is not None
                    for key in (
                        "savings_per_case",
                        "savings_per_unit",
                        "min_cases",
                        "deal_total",
                    )
                )
                if has_deal:
                    discount = product.get("savings_per_case")
                    if discount is None:
                        discount = product.get("savings_per_unit")
                    self.insert_deal(
                        shared_product_id,
                        deal_title=product.get("deal_type") or "SGProof deal",
                        deal_number=f"SGPROOF-{product.get('product_id') or shared_product_id}",
                        sku_number=product.get("product_id"),
                        quantity_type="Exact Qty Only",
                        quantity=product.get("min_cases"),
                        quantity_unit="Cases" if product.get("min_cases") is not None else None,
                        estimated_bottle_price=unit_price,
                        cse_price=case_price,
                        total_cse_price=product.get("deal_total"),
                        action_type="Discount",
                        discount_per_unit=discount,
                        is_mix_and_match=0,
                        deal_obj_type=product.get("deal_type"),
                    )

                saved += 1
            except Exception as error:
                logger.warning("Error saving SGProof product %s: %s", name, error)

        logger.info("Saved %s/%s SGProof products to shared database", saved, len(products))
        return saved