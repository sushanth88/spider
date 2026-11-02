#!/usr/bin/env python3
"""
Price Scraper CLI

Scrapes product prices from breakthrubev.com and stores them in SQLite database.
"""

import os
import sys
import logging
import argparse
from dotenv import load_dotenv
from database import Database
from scraper import ProductScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from environment variables."""
    load_dotenv()

    username = os.getenv('WEBSITE_USERNAME')
    password = os.getenv('WEBSITE_PASSWORD')
    db_path = os.getenv('DATABASE_PATH', 'data/products.db')

    if not username or not password:
        logger.error("Missing required environment variables: WEBSITE_USERNAME and/or WEBSITE_PASSWORD")
        logger.error("Please copy .env.example to .env and fill in your credentials")
        sys.exit(1)

    return {
        'username': username,
        'password': password,
        'db_path': db_path
    }


def main():
    """Main execution function."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Scrape product prices from Breakthru Beverage portal')
    parser.add_argument('--query', '-q', type=str, default='spirits',
                       help='Search query for products (default: spirits)')
    parser.add_argument('--infinite-scroll', action='store_true', default=False,
                       help='Enable infinite scroll to collect all products (may take 6-10 hours)')
    parser.add_argument('--scroll-pause', type=float, default=2.0,
                       help='Seconds to wait after each scroll (default: 2.0)')
    parser.add_argument('--scroll-max-attempts', type=int, default=100,
                       help='Maximum scroll attempts (default: 100)')
    parser.add_argument('--scroll-threshold', type=int, default=3,
                       help='Stop after N scrolls with no new products (default: 3)')
    args = parser.parse_args()

    logger.info(f"Starting price scraper for query: '{args.query}'...")
    if args.infinite_scroll:
        logger.info("Infinite scroll ENABLED - this will collect all products (may take several hours)")
        logger.info(f"Scroll settings: pause={args.scroll_pause}s, max_attempts={args.scroll_max_attempts}, threshold={args.scroll_threshold}")

    # Load configuration
    config = load_config()

    # Initialize database
    logger.info(f"Initializing database at {config['db_path']}")
    db = Database(config['db_path'])

    # Initialize scraper with database for real-time insertion
    scraper = ProductScraper(
        username=config['username'],
        password=config['password'],
        headless=True,
        search_query=args.query,
        enable_infinite_scroll=args.infinite_scroll,
        scroll_pause_time=args.scroll_pause,
        scroll_max_attempts=args.scroll_max_attempts,
        scroll_no_new_products_threshold=args.scroll_threshold,
        database=db  # Pass database for real-time insertion
    )

    try:
        # Scrape products
        logger.info("Starting web scraping...")
        products = scraper.scrape_products(max_retries=3)

        if not products:
            logger.warning("No products were scraped")
            return

        # Store products and prices (skip if already inserted in real-time)
        logger.info(f"Verifying {len(products)} products in database...")
        new_products = 0
        new_prices = 0
        price_changes = 0

        # If database was passed to scraper, products were already inserted in real-time
        # This loop is now just for statistics and verification
        for product_data in products:
            # Insert or get product with all fields
            product_id = db.insert_product(
                name=product_data['name'],
                url=product_data.get('url'),
                source='Breakthru Beverage',
                product_id=product_data.get('product_id'),
                bottle_upc=product_data.get('bottle_upc'),
                case_upc=product_data.get('case_upc'),
                size=product_data.get('size'),
                qty_per_case=product_data.get('qty_per_case'),
                proof_abv=product_data.get('proof_abv'),
                container_type=product_data.get('container_type'),
                brand=product_data.get('brand'),
                supplier=product_data.get('supplier'),
                country_of_origin=product_data.get('country_of_origin'),
                region=product_data.get('region'),
                categories=product_data.get('categories'),
                product_details=product_data.get('product_details')
            )

            if product_id:
                # Get previous price for comparison
                history = db.get_price_history(product_id)
                previous_price = history[0]['price'] if history else None

                # Insert new price
                was_inserted = db.insert_price(
                    product_id=product_id,
                    price=product_data['price'],
                    scraped_at=product_data['scraped_at']
                )

                if was_inserted:
                    new_prices += 1

                    # Check for price change
                    if previous_price is not None and previous_price != product_data['price']:
                        price_changes += 1
                        change = product_data['price'] - previous_price
                        logger.info(
                            f"Price change detected: {product_data['name']} - "
                            f"${previous_price:.2f} -> ${product_data['price']:.2f} "
                            f"({change:+.2f})"
                        )
                    elif previous_price is None:
                        new_products += 1

                # Handle deals if present
                if 'deals' in product_data and product_data['deals']:
                    # Delete old deals for this product
                    deleted_count = db.delete_deals_for_product(product_id)
                    if deleted_count > 0:
                        logger.info(f"Deleted {deleted_count} old deals for {product_data['name']}")

                    # Insert new deals
                    deals_inserted = 0
                    for deal in product_data['deals']:
                        if db.insert_deal(product_id, **deal):
                            deals_inserted += 1

                    if deals_inserted > 0:
                        logger.info(f"Inserted {deals_inserted} deals for {product_data['name']}")
            else:
                logger.error(f"Failed to insert product: {product_data['name']}")

        logger.info("=" * 60)
        logger.info("Scraping Summary:")
        logger.info(f"  Total products scraped: {len(products)}")
        logger.info(f"  New products added: {new_products}")
        logger.info(f"  New price entries: {new_prices}")
        logger.info(f"  Price changes detected: {price_changes}")
        logger.info("=" * 60)
        logger.info("Scraping completed successfully!")

    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
