import tempfile
import unittest
from pathlib import Path

from sgproof_database_adapter import Database


class TestSGProofDatabaseAdapter(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database = Database(str(Path(self.temp_directory.name) / "shared.db"))

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_saves_sgproof_product_price_and_deal_to_shared_tables(self):
        saved = self.database.save_products([
            {
                "name": "SGProof Test Product",
                "product_id": "SG-100",
                "deal_type": "Case Discount",
                "size": "750 ml",
                "units_per_case": 12,
                "url": "https://shop.sgproof.com/deals/showdeal/SG-100",
                "min_cases": 3,
                "price_per_case": 120.0,
                "price_per_unit": 10.0,
                "savings_per_case": 12.0,
                "savings_per_unit": 1.0,
                "deal_total": 360.0,
            }
        ])

        products = self.database.get_all_products_with_latest_price()
        self.assertEqual(saved, 1)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["source"], "SGProof")
        self.assertEqual(products[0]["latest_price"], 120.0)
        deals = self.database.get_deals_for_product(products[0]["id"])
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0]["cse_price"], 120.0)
        self.assertEqual(deals[0]["discount_per_unit"], 12.0)

    def test_repeated_scrape_updates_one_deal_record(self):
        product = {
            "name": "SGProof Test Product",
            "product_id": "SG-100",
            "deal_type": "Case Discount",
            "size": "750 ml",
            "units_per_case": 12,
            "url": "https://shop.sgproof.com/deals/showdeal/SG-100",
            "min_cases": 3,
            "price_per_case": 120.0,
            "price_per_unit": 10.0,
            "savings_per_case": 12.0,
            "deal_total": 360.0,
        }

        self.database.save_products([product])
        self.database.save_products([product])

        products = self.database.get_all_products_with_latest_price()
        self.assertEqual(len(products), 1)
        self.assertEqual(len(self.database.get_deals_for_product(products[0]["id"])), 1)


if __name__ == "__main__":
    unittest.main()