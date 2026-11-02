-- PostgreSQL Initialization Script for Spider Price Tracker
-- This script runs automatically when the container is first created
-- Schema matches database.py

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone
SET timezone = 'UTC';

-- =====================================
-- PRODUCTS TABLE
-- =====================================
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT,
    product_id TEXT,
    bottle_upc TEXT,
    case_upc TEXT,
    size TEXT,
    qty_per_case INTEGER,
    proof_abv TEXT,
    container_type TEXT,
    brand TEXT,
    supplier TEXT,
    source TEXT,
    country_of_origin TEXT,
    region TEXT,
    categories TEXT,
    deal_summary TEXT,
    product_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, url)
);

-- =====================================
-- PRICE HISTORY TABLE
-- =====================================
CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    price REAL NOT NULL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, price, scraped_at)
);

-- =====================================
-- DEALS TABLE
-- =====================================
CREATE TABLE IF NOT EXISTS deals (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    deal_title TEXT,
    deal_number TEXT,
    sku_number TEXT,
    usage_limit TEXT,
    quantity_type TEXT,
    bottle_fees_applicable INTEGER,
    quantity REAL,
    quantity_unit TEXT,
    estimated_bottle_price REAL,
    cse_price REAL,
    total_estimated_price REAL,
    total_cse_price REAL,
    action_type TEXT,
    discount_per_unit REAL,
    is_mix_and_match INTEGER,
    deal_obj_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, deal_number, quantity, quantity_unit)
);

-- =====================================
-- INDEXES FOR PERFORMANCE
-- =====================================

-- Price history indexes
CREATE INDEX IF NOT EXISTS idx_price_history_product_id
    ON price_history(product_id);

CREATE INDEX IF NOT EXISTS idx_price_history_scraped_at
    ON price_history(scraped_at DESC);

-- Deals indexes
CREATE INDEX IF NOT EXISTS idx_deals_product_id
    ON deals(product_id);

CREATE INDEX IF NOT EXISTS idx_deals_deal_number
    ON deals(deal_number);

-- =====================================
-- OPTIONAL: READ-ONLY USER
-- =====================================
-- Uncomment to create a read-only user for reporting/analytics
-- CREATE USER spider_readonly WITH PASSWORD 'readonly_password_change_me';
-- GRANT CONNECT ON DATABASE spider_dev TO spider_readonly;
-- GRANT USAGE ON SCHEMA public TO spider_readonly;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO spider_readonly;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO spider_readonly;

-- Log success
DO $$
BEGIN
    RAISE NOTICE '✅ Spider Price Tracker schema initialized successfully';
END $$;
