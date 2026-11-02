import unittest

from vtinfo_scraper import VTInfoScraper


class TestVTInfoScraper(unittest.TestCase):
    def test_vendor_urls_use_distinct_wholesaler_ids(self):
        nks = VTInfoScraper(vendor="nks")
        standard = VTInfoScraper(vendor="standard")

        self.assertIn("/00131/retailer/15786", nks.catalog_url)
        self.assertIn("/00128/retailer/15786", standard.catalog_url)

    def test_extracts_case_price_from_detail_text(self):
        self.assertEqual(VTInfoScraper._extract_price(["$24.00/Case"]), 24.0)
        self.assertEqual(VTInfoScraper._extract_price(["$9.92/Unit"]), 9.92)
        self.assertIsNone(VTInfoScraper._extract_price(["Price unavailable"]))

    def test_parses_vtinfo_deal_title(self):
        deal = VTInfoScraper._parse_deal(
            "$1.00 Off per Case with a minimum order of 3 Cases",
            "12966",
            "713",
            True,
        )

        self.assertEqual(deal["deal_number"], "713")
        self.assertEqual(deal["sku_number"], "12966")
        self.assertEqual(deal["quantity"], 3.0)
        self.assertEqual(deal["quantity_unit"], "Cases")
        self.assertEqual(deal["discount_per_unit"], 1.0)
        self.assertEqual(deal["is_mix_and_match"], 1)

    def test_extracts_upc_with_digit_groups(self):
        lines = ["Case UPC", "10684746403607", "Retail UPC", "6", "84746", "40441", "6"]

        self.assertEqual(VTInfoScraper._extract_upc(lines, "Case UPC"), "10684746403607")
        self.assertEqual(VTInfoScraper._extract_upc(lines, "Retail UPC"), "684746404416")


if __name__ == "__main__":
    unittest.main()