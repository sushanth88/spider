#!/usr/bin/env python3
"""
Flask Web Application for Product Price Tracking

Provides a read-only web interface to view product prices and history.
"""

import os
from flask import Flask, render_template, request
from dotenv import load_dotenv
from database import Database

load_dotenv()

app = Flask(__name__)
app.config['DATABASE_PATH'] = os.getenv('DATABASE_PATH', 'data/products.db')


def get_db():
    """Get database instance."""
    return Database(app.config['DATABASE_PATH'])


@app.route('/')
def index():
    """Home page showing all products with latest prices."""
    db = get_db()

    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '')
    brand_filter = request.args.get('brand', '')
    deal_filter = request.args.get('deals', '')
    source_filter = request.args.get('source', '')

    all_products = db.get_all_products_with_latest_price()
    products = all_products.copy()

    # Apply filters
    if search_query:
        products = [p for p in products if search_query.lower() in p['name'].lower() or
                   (p.get('brand') and search_query.lower() in p['brand'].lower())]

    if category_filter:
        products = [p for p in products if p.get('categories') and category_filter in p['categories']]

    if brand_filter:
        products = [p for p in products if p.get('brand') == brand_filter]

    if source_filter:
        products = [p for p in products if p.get('source') == source_filter]

    if deal_filter == 'yes':
        products = [p for p in products if p.get('deal_count', 0) > 0]
    elif deal_filter == 'no':
        products = [p for p in products if p.get('deal_count', 0) == 0]

    stats = db.get_statistics()

    # Get unique categories and brands for filters
    categories = set()
    brands = set()
    sources = set()
    for p in all_products:
        if p.get('categories'):
            for cat in p['categories'].split(', '):
                categories.add(cat.strip())
        if p.get('brand'):
            brands.add(p['brand'])
        sources.add(p.get('source') or 'Unknown')

    # Calculate statistics for filtered results
    filtered_stats = {
        'total_products': len(products),
        'total_deals': sum(p.get('deal_count', 0) for p in products),
        'products_with_deals': len([p for p in products if p.get('deal_count', 0) > 0]),
        'by_spirit_type': {}
    }

    # Calculate spirit type breakdown for filtered results
    spirit_counts = {}
    for p in products:
        if p.get('categories'):
            # Extract spirit type from categories
            categories_list = p['categories'].split(', ')
            for cat in categories_list:
                cat = cat.strip()
                # Count each category
                if cat:
                    spirit_counts[cat] = spirit_counts.get(cat, 0) + 1

    # Convert to list format sorted by count
    filtered_stats['by_spirit_type'] = [
        {'spirit_type': spirit, 'count': count}
        for spirit, count in sorted(spirit_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    last_scrape = db.get_last_scrape_time()
    price_changes = db.get_price_changes()

    return render_template(
        'index.html',
        products=products,
        last_scrape=last_scrape,
        price_changes=price_changes,
        total_products=len(products),
        stats=stats,
        filtered_stats=filtered_stats,
        categories=sorted(categories),
        brands=sorted(brands),
        sources=sorted(sources),
        search_query=search_query,
        category_filter=category_filter,
        brand_filter=brand_filter,
        deal_filter=deal_filter,
        source_filter=source_filter
    )


@app.route('/stats')
def statistics():
    """Statistics and dashboard page."""
    db = get_db()

    # Get all statistics
    stats = db.get_statistics()
    price_changes = db.get_price_changes()
    last_scrape = db.get_last_scrape_time()

    # Get all products for additional stats
    all_products = db.get_all_products_with_latest_price()
    total_products = len(all_products)

    return render_template(
        'statistics.html',
        stats=stats,
        price_changes=price_changes,
        last_scrape=last_scrape,
        total_products=total_products
    )


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page showing full price history."""
    db = get_db()
    product = db.get_product_by_id(product_id)

    if not product:
        return "Product not found", 404

    price_history = db.get_price_history(product_id)
    deals = db.get_deals_for_product(product_id)

    # Calculate statistics
    if price_history:
        prices = [entry['price'] for entry in price_history]
        stats = {
            'current': prices[0] if prices else None,
            'highest': max(prices),
            'lowest': min(prices),
            'average': sum(prices) / len(prices),
            'total_changes': len(price_history)
        }
    else:
        stats = None

    return render_template(
        'product_detail.html',
        product=product,
        price_history=price_history,
        deals=deals,
        stats=stats
    )


@app.template_filter('format_price')
def format_price(value):
    """Format price as currency."""
    if value is None:
        return 'N/A'
    return f'${value:.2f}'


@app.template_filter('format_datetime')
def format_datetime(value):
    """Format datetime string."""
    if not value:
        return 'Never'
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return value


@app.template_filter('price_change_class')
def price_change_class(value):
    """Return CSS class for price change."""
    if value is None or value == 0:
        return 'neutral'
    return 'increase' if value > 0 else 'decrease'


if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    app.run(host=host, port=port, debug=debug)
