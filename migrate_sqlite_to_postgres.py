#!/usr/bin/env python3
"""Import products, prices, and deals from SQLite into the configured PostgreSQL database."""

import argparse
import logging
import os
import sqlite3
from datetime import datetime

from database import Database


logger = logging.getLogger(__name__)

PRODUCT_FIELDS = (
    "product_id",
    "bottle_upc",
    "case_upc",
    "size",
    "qty_per_case",
    "proof_abv",
    "container_type",
    "brand",
    "supplier",
    "source",
    "country_of_origin",
    "region",
    "categories",
    "deal_summary",
    "product_details",
)

DEAL_FIELDS = (
    "deal_title",
    "deal_number",
    "sku_number",
    "usage_limit",
    "quantity_type",
    "bottle_fees_applicable",
    "quantity",
    "quantity_unit",
    "estimated_bottle_price",
    "cse_price",
    "total_estimated_price",
    "total_cse_price",
    "action_type",
    "discount_per_unit",
    "is_mix_and_match",
    "deal_obj_type",
)


def _price_timestamp(value):
    timestamp = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")


def migrate(sqlite_path):
    if not os.path.isfile(sqlite_path):
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    database = Database()
    if database.db_type != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL for this migration")

    source_connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    source_connection.row_factory = sqlite3.Row
    product_columns = {
        row[1] for row in source_connection.execute("PRAGMA table_info(products)")
    }
    product_rows = source_connection.execute("SELECT * FROM products ORDER BY id").fetchall()
    prices_added = 0
    deals_added = 0

    try:
        for product_row in product_rows:
            product = dict(product_row)
            product_values = {
                field: product.get(field)
                for field in PRODUCT_FIELDS
                if field in product_columns
            }
            product_id = database.insert_product(
                name=product["name"],
                url=product.get("url"),
                **product_values,
            )
            if not product_id:
                logger.warning("Skipping product with no destination ID: %s", product["name"])
                continue

            existing_prices = {
                (float(entry["price"]), str(entry["scraped_at"]))
                for entry in database.get_price_history(product_id)
            }
            price_rows = source_connection.execute(
                "SELECT price, scraped_at FROM price_history WHERE product_id = ?",
                (product["id"],),
            ).fetchall()
            for price_row in price_rows:
                price_key = (float(price_row["price"]), str(price_row["scraped_at"]))
                if price_key in existing_prices:
                    continue
                if database.insert_price(
                    product_id,
                    price_key[0],
                    _price_timestamp(price_row["scraped_at"]),
                ):
                    prices_added += 1
                    existing_prices.add(price_key)

            existing_deals = {
                (deal.get("deal_number"), deal.get("quantity"), deal.get("quantity_unit"))
                for deal in database.get_deals_for_product(product_id)
            }
            deal_rows = source_connection.execute(
                "SELECT * FROM deals WHERE product_id = ?",
                (product["id"],),
            ).fetchall()
            for deal_row in deal_rows:
                deal = dict(deal_row)
                deal_key = (deal.get("deal_number"), deal.get("quantity"), deal.get("quantity_unit"))
                if deal_key in existing_deals:
                    continue
                deal_values = {field: deal.get(field) for field in DEAL_FIELDS if field in deal}
                if database.insert_deal(product_id, **deal_values):
                    deals_added += 1
                    existing_deals.add(deal_key)

    finally:
        source_connection.close()

    logger.info(
        "Migration complete: %s products processed, %s prices and %s deals added",
        len(product_rows),
        prices_added,
        deals_added,
    )
    migrate_sgproof(database)


def migrate_sgproof(database):
    """Import the SGProof-specific tables already stored in PostgreSQL."""
    if database.db_type != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL for SGProof migration")

    with database.get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'sgproof_products'
        """)
        if not cursor.fetchone():
            logger.info("No SGProof tables found; skipping SGProof import")
            return

        cursor.execute("""
            CREATE OR REPLACE FUNCTION spider_sync_sgproof_product()
            RETURNS trigger AS $$
            DECLARE
                shared_product_id INTEGER;
            BEGIN
                INSERT INTO products (
                    name, url, product_id, size, qty_per_case, source,
                    categories, deal_summary, product_details
                )
                VALUES (
                    NEW.name, NEW.url, NEW.product_id, NEW.size,
                    NEW.units_per_case, 'SGProof', NEW.deal_type,
                    NEW.deal_type, NEW.deal_type
                )
                ON CONFLICT (name, url) DO UPDATE SET
                    product_id = COALESCE(EXCLUDED.product_id, products.product_id),
                    size = COALESCE(EXCLUDED.size, products.size),
                    qty_per_case = COALESCE(EXCLUDED.qty_per_case, products.qty_per_case),
                    source = CASE
                        WHEN products.source IS NULL OR products.source IN ('', 'SGProof')
                        THEN 'SGProof' ELSE products.source
                    END,
                    categories = COALESCE(EXCLUDED.categories, products.categories),
                    deal_summary = COALESCE(EXCLUDED.deal_summary, products.deal_summary),
                    product_details = COALESCE(EXCLUDED.product_details, products.product_details)
                RETURNING id INTO shared_product_id;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION spider_sync_sgproof_price()
            RETURNS trigger AS $$
            DECLARE
                sg_product sgproof_products%ROWTYPE;
                shared_product_id INTEGER;
                shared_price NUMERIC(10, 2);
            BEGIN
                SELECT * INTO sg_product
                FROM sgproof_products
                WHERE id = NEW.product_id;

                IF NOT FOUND THEN
                    RETURN NEW;
                END IF;

                INSERT INTO products (
                    name, url, product_id, size, qty_per_case, source,
                    categories, deal_summary, product_details
                )
                VALUES (
                    sg_product.name, sg_product.url, sg_product.product_id,
                    sg_product.size, sg_product.units_per_case, 'SGProof',
                    sg_product.deal_type, sg_product.deal_type, sg_product.deal_type
                )
                ON CONFLICT (name, url) DO UPDATE SET
                    product_id = COALESCE(EXCLUDED.product_id, products.product_id),
                    size = COALESCE(EXCLUDED.size, products.size),
                    qty_per_case = COALESCE(EXCLUDED.qty_per_case, products.qty_per_case),
                    source = CASE
                        WHEN products.source IS NULL OR products.source IN ('', 'SGProof')
                        THEN 'SGProof' ELSE products.source
                    END,
                    categories = COALESCE(EXCLUDED.categories, products.categories),
                    deal_summary = COALESCE(EXCLUDED.deal_summary, products.deal_summary),
                    product_details = COALESCE(EXCLUDED.product_details, products.product_details)
                RETURNING id INTO shared_product_id;

                shared_price := COALESCE(NEW.price_per_case, NEW.price_per_unit);
                IF shared_price IS NOT NULL THEN
                    INSERT INTO price_history (product_id, price, scraped_at)
                    VALUES (shared_product_id, shared_price, NEW.scraped_at)
                    ON CONFLICT (product_id, price, scraped_at) DO NOTHING;
                END IF;

                DELETE FROM deals
                WHERE product_id = shared_product_id AND deal_number LIKE 'SGPROOF-%';

                IF NEW.savings_per_case IS NOT NULL
                   OR NEW.savings_per_unit IS NOT NULL
                   OR NEW.min_cases IS NOT NULL
                   OR NEW.deal_total IS NOT NULL THEN
                    INSERT INTO deals (
                        product_id, deal_title, deal_number, sku_number,
                        quantity_type, quantity, quantity_unit,
                        estimated_bottle_price, cse_price, total_cse_price,
                        action_type, discount_per_unit, is_mix_and_match, deal_obj_type
                    )
                    VALUES (
                        shared_product_id,
                        COALESCE(sg_product.deal_type, 'SGProof deal'),
                        'SGPROOF-' || NEW.product_id,
                        sg_product.product_id,
                        'Exact Qty Only', NEW.min_cases, 'Cases',
                        NEW.price_per_unit, NEW.price_per_case, NEW.deal_total,
                        'Discount', COALESCE(NEW.savings_per_case, NEW.savings_per_unit),
                        0, sg_product.deal_type
                    )
                    ON CONFLICT (product_id, deal_number, quantity, quantity_unit)
                    DO UPDATE SET
                        deal_title = EXCLUDED.deal_title,
                        estimated_bottle_price = EXCLUDED.estimated_bottle_price,
                        cse_price = EXCLUDED.cse_price,
                        total_cse_price = EXCLUDED.total_cse_price,
                        discount_per_unit = EXCLUDED.discount_per_unit,
                        deal_obj_type = EXCLUDED.deal_obj_type;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        cursor.execute("DROP TRIGGER IF EXISTS spider_sync_sgproof_product_trigger ON sgproof_products")
        cursor.execute("""
            CREATE TRIGGER spider_sync_sgproof_product_trigger
            AFTER INSERT OR UPDATE ON sgproof_products
            FOR EACH ROW EXECUTE FUNCTION spider_sync_sgproof_product()
        """)
        cursor.execute("DROP TRIGGER IF EXISTS spider_sync_sgproof_price_trigger ON sgproof_price_history")
        cursor.execute("""
            CREATE TRIGGER spider_sync_sgproof_price_trigger
            AFTER INSERT OR UPDATE ON sgproof_price_history
            FOR EACH ROW EXECUTE FUNCTION spider_sync_sgproof_price()
        """)

        cursor.execute("""
            WITH unique_products AS (
                SELECT DISTINCT ON (name, url)
                    name, url, product_id, size, units_per_case, deal_type
                FROM sgproof_products
                ORDER BY name, url, id DESC
            )
            INSERT INTO products (
                name, url, product_id, size, qty_per_case, source,
                deal_summary, product_details
            )
            SELECT
                sg.name,
                sg.url,
                sg.product_id,
                sg.size,
                sg.units_per_case,
                'SGProof',
                sg.deal_type,
                sg.deal_type
            FROM unique_products sg
            ON CONFLICT (name, url) DO UPDATE SET
                product_id = COALESCE(products.product_id, EXCLUDED.product_id),
                size = COALESCE(products.size, EXCLUDED.size),
                qty_per_case = COALESCE(products.qty_per_case, EXCLUDED.qty_per_case),
                source = CASE
                    WHEN products.source IS NULL OR products.source = '' THEN EXCLUDED.source
                    ELSE products.source
                END,
                deal_summary = COALESCE(products.deal_summary, EXCLUDED.deal_summary),
                product_details = COALESCE(products.product_details, EXCLUDED.product_details)
        """)
        products_processed = cursor.rowcount

        cursor.execute("""
            INSERT INTO price_history (product_id, price, scraped_at)
            SELECT
                p.id,
                COALESCE(history.price_per_case, history.price_per_unit),
                history.scraped_at
            FROM sgproof_price_history history
            JOIN sgproof_products sg ON sg.id = history.product_id
            JOIN products p ON p.name = sg.name AND p.url = sg.url AND p.source = 'SGProof'
            WHERE COALESCE(history.price_per_case, history.price_per_unit) IS NOT NULL
            ON CONFLICT (product_id, price, scraped_at) DO NOTHING
        """)
        prices_added = cursor.rowcount

        cursor.execute("""
            WITH latest_history AS (
                SELECT
                    sg.name,
                    sg.url,
                    sg.product_id AS vendor_product_id,
                    sg.deal_type,
                    history.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY sg.name, sg.url
                        ORDER BY history.scraped_at DESC, history.id DESC
                    ) AS row_number
                FROM sgproof_price_history history
                JOIN sgproof_products sg ON sg.id = history.product_id
            )
            INSERT INTO deals (
                product_id, deal_title, deal_number, sku_number,
                quantity_type, quantity, quantity_unit,
                estimated_bottle_price, cse_price, total_cse_price,
                action_type, discount_per_unit, is_mix_and_match, deal_obj_type
            )
            SELECT
                p.id,
                COALESCE(history.deal_type, 'SGProof deal'),
                'SGPROOF-' || history.id,
                history.vendor_product_id,
                'Exact Qty Only',
                history.min_cases,
                'Cases',
                history.price_per_unit,
                history.price_per_case,
                history.deal_total,
                'Discount',
                history.savings_per_case,
                0,
                history.deal_type
            FROM latest_history history
            JOIN products p ON p.name = history.name AND p.url = history.url AND p.source = 'SGProof'
            WHERE history.row_number = 1
              AND (history.savings_per_case IS NOT NULL OR history.min_cases IS NOT NULL)
            ON CONFLICT (product_id, deal_number, quantity, quantity_unit) DO NOTHING
        """)
        deals_added = cursor.rowcount

    logger.info(
        "SGProof import complete: %s products processed, %s prices and %s deals added",
        products_processed,
        prices_added,
        deals_added,
    )


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Import SQLite tracker data into PostgreSQL")
    parser.add_argument("--sqlite-path", default="data/products.db")
    parser.add_argument("--sgproof-only", action="store_true", help="Sync SGProof tables already in PostgreSQL")
    args = parser.parse_args()
    if args.sgproof_only:
        migrate_sgproof(Database())
    else:
        migrate(args.sqlite_path)


if __name__ == "__main__":
    main()