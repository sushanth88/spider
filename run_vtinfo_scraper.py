#!/usr/bin/env python3
import argparse
import logging
import os

from dotenv import load_dotenv

from database import Database
from vtinfo_scraper import VTInfoScraper


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    load_dotenv(".env")
    load_dotenv("VT_info.env", override=True)
    parser = argparse.ArgumentParser(description="Scrape NKS or Standard Distributing from VTInfo")
    parser.add_argument("--vendor", choices=("nks", "standard"), required=True)
    parser.add_argument("--retailer-id", default=os.getenv("VTINFO_RETAILER_ID", "15786"))
    parser.add_argument("--max-products", type=int, help="Limit products for a short test run")
    parser.add_argument("--headed", action="store_true", help="Show the browser for MFA or manual sign-in")
    parser.add_argument("--page-pause", type=float, default=0.25, help="Delay between product pages in seconds")
    args = parser.parse_args()

    if args.max_products is not None and args.max_products < 1:
        parser.error("--max-products must be at least 1")

    username = os.getenv("VTINFO_USERNAME")
    password = os.getenv("VTINFO_PASSWORD")
    if (not username or not password) and not args.headed:
        parser.error("Set VTINFO_USERNAME and VTINFO_PASSWORD, or use --headed for manual sign-in")

    database = Database(os.getenv("DATABASE_PATH", "data/products.db"))
    scraper = VTInfoScraper(
        username=username,
        password=password,
        vendor=args.vendor,
        retailer_id=args.retailer_id,
        headless=not args.headed,
        page_pause=args.page_pause,
        database=database,
    )

    products = scraper.scrape_products(max_products=args.max_products)
    logger.info("Scrape complete: %s %s products", len(products), args.vendor)


if __name__ == "__main__":
    main()