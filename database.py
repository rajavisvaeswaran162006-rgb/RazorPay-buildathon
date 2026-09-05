"""
database.py — TechMart AI Shopping Agent
=========================================
Reusable SQLite database layer for product catalog, orders & audit logs.

Tables used (from existing orders.db):
  - products:    id, name, category, price, description, stock
  - orders:      id, order_id, customer_id, receipt_id, product_name, ...
  - order_items: id, order_id, product_id, quantity
  - audit_logs:  id, timestamp, event_type, action, ...
"""

import sqlite3
import logging
import json
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = "orders.db"


# ─────────────────────────────────────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """
    Open a connection to the SQLite database.
    Returns rows as dict-like sqlite3.Row objects for easy column access.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Product queries
# ─────────────────────────────────────────────────────────────────────────────

def search_products(
    keyword: str = "",
    category: str = "",
    max_price: float | None = None,
    min_price: float | None = None,
    in_stock_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Search the products table with optional filters.

    Parameters
    ----------
    keyword       : matches against product name OR description (case-insensitive)
    category      : exact category filter (case-insensitive)
    max_price     : maximum price in INR (inclusive)
    min_price     : minimum price in INR (inclusive)
    in_stock_only : if True, only return products with stock > 0

    Returns
    -------
    List of product dicts sorted by price ascending.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Build query dynamically with parameterized placeholders
        conditions: list[str] = []
        params: list[Any] = []

        if keyword:
            conditions.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)")
            like_pattern = f"%{keyword.lower()}%"
            params.extend([like_pattern, like_pattern])

        if category:
            cat_clean = category.lower().strip()
            cat_singular = cat_clean.rstrip("s") if cat_clean.endswith("s") and len(cat_clean) > 3 else cat_clean
            cat_plural = cat_singular + "s"
            conditions.append("(LOWER(category) = ? OR LOWER(category) = ? OR LOWER(category) = ?)")
            params.extend([cat_clean, cat_singular, cat_plural])

        if max_price is not None:
            conditions.append("price <= ?")
            params.append(max_price)

        if min_price is not None:
            conditions.append("price >= ?")
            params.append(min_price)

        if in_stock_only:
            conditions.append("stock > 0")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"SELECT * FROM products {where_clause} ORDER BY price ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except sqlite3.Error as e:
        logger.error(f"Database error in search_products: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_product(product_id: int) -> dict[str, Any] | None:
    """
    Fetch a single product by its ID.
    Returns a product dict or None if not found.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    except sqlite3.Error as e:
        logger.error(f"Database error in get_product: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_categories() -> list[str]:
    """
    Return a sorted list of distinct product categories.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
        return [row["category"] for row in cursor.fetchall()]

    except sqlite3.Error as e:
        logger.error(f"Database error in get_categories: {e}")
        return []
    finally:
        if conn:
            conn.close()


def update_stock(product_id: int, quantity_delta: int) -> bool:
    """
    Adjust a product's stock by quantity_delta (negative to reduce).
    Returns True if the update succeeded and stock stayed >= 0.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check current stock first
        cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            return False

        new_stock = row["stock"] + quantity_delta
        if new_stock < 0:
            return False

        cursor.execute(
            "UPDATE products SET stock = ? WHERE id = ?",
            (new_stock, product_id),
        )
        conn.commit()
        return True

    except sqlite3.Error as e:
        logger.error(f"Database error in update_stock: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_product_count() -> int:
    """Return the total number of products in the database."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM products")
        return cursor.fetchone()["cnt"]
    except sqlite3.Error as e:
        logger.error(f"Database error in get_product_count: {e}")
        return 0
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Cross-sell & Related Products
# ─────────────────────────────────────────────────────────────────────────────

RELATED_CATEGORY_MAP: dict[str, list[str]] = {
    "Laptop": ["Mouse", "Laptop Bags", "Laptop Bag", "Chargers", "Charger", "Headphones", "Power Banks", "Storage"],
    "Laptops": ["Mouse", "Laptop Bags", "Laptop Bag", "Chargers", "Charger", "Headphones", "Power Banks", "Storage"],
    "Smartphone": ["Chargers", "Charger", "Power Banks", "Power Bank", "Headphones", "Smartwatches", "Smartwatch"],
    "Smartphones": ["Chargers", "Charger", "Power Banks", "Power Bank", "Headphones", "Smartwatches", "Smartwatch"],
    "Tablet": ["Chargers", "Charger", "Power Banks", "Power Bank", "Headphones", "Smartwatches", "Smartwatch"],
    "Tablets": ["Chargers", "Charger", "Power Banks", "Power Bank", "Headphones", "Smartwatches", "Smartwatch"],
    "Headphones": ["Speakers", "Speaker", "Power Banks", "Power Bank", "Chargers", "Charger"],
    "Speaker": ["Headphones", "Power Banks", "Power Bank"],
    "Speakers": ["Headphones", "Power Banks", "Power Bank"],
    "Mouse": ["Keyboards", "Keyboard", "Monitors", "Monitor", "Laptop Bags", "Laptop Bag"],
    "Mice": ["Keyboards", "Keyboard", "Monitors", "Monitor"],
    "Keyboard": ["Mouse", "Monitors", "Monitor"],
    "Keyboards": ["Mouse", "Monitors", "Monitor"],
    "Monitor": ["Keyboards", "Keyboard", "Mouse"],
    "Monitors": ["Keyboards", "Keyboard", "Mouse"],
    "Smartwatch": ["Smartphones", "Smartphone", "Headphones", "Chargers", "Charger"],
    "Smartwatches": ["Smartphones", "Smartphone", "Headphones", "Chargers", "Charger"],
    "Router": ["Laptops", "Laptop", "Monitors", "Monitor"],
    "Routers": ["Laptops", "Laptop", "Monitors", "Monitor"],
    "Charger": ["Power Banks", "Power Bank", "Smartphones", "Smartphone"],
    "Chargers": ["Power Banks", "Power Bank", "Smartphones", "Smartphone"],
    "Power Bank": ["Chargers", "Charger", "Smartphones", "Smartphone"],
    "Power Banks": ["Chargers", "Charger", "Smartphones", "Smartphone"],
    "Laptop Bag": ["Mouse", "Chargers", "Charger"],
    "Laptop Bags": ["Mouse", "Chargers", "Charger"],
    "Storage": ["Laptops", "Laptop", "Laptop Bags", "Mouse"],
    "Accessories": ["Mouse", "Chargers", "Charger"],
}


def get_related_products(
    product_id: int,
    limit: int = 2,
    exclude_ids: list[int] | set[int] | None = None,
    preferred_category: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch complementary/related in-stock products for cross-sell or upsell.
    Supports excluding already suggested product IDs to ensure diverse recommendations across cards.
    Prioritizes brand affinity (e.g. HP backpack for HP laptop) and category diversity.
    """
    target = get_product(product_id)
    if not target:
        return []

    cat = target.get("category", "")
    complementary_cats = list(RELATED_CATEGORY_MAP.get(cat, ["Accessories", "Mouse"]))

    # If preferred category is specified and in complementary list, move it to the front
    if preferred_category and preferred_category in complementary_cats:
        complementary_cats.remove(preferred_category)
        complementary_cats.insert(0, preferred_category)

    exclude_set = set(exclude_ids or [])
    exclude_set.add(product_id)

    target_name = target.get("name", "")
    target_brand = target_name.split()[0].lower() if target_name else ""

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cat_placeholders = ",".join("?" * len(complementary_cats))
        ex_placeholders = ",".join("?" * len(exclude_set))

        query = f"""
            SELECT * FROM products
            WHERE category IN ({cat_placeholders})
              AND id NOT IN ({ex_placeholders})
              AND stock > 0
        """
        params = list(complementary_cats) + list(exclude_set)
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

        # Safe fallback: if excluded_ids eliminated all products, retry without excluding previous slots
        if not rows:
            fallback_query = f"""
                SELECT * FROM products
                WHERE category IN ({cat_placeholders})
                  AND id != ?
                  AND stock > 0
                ORDER BY price ASC
                LIMIT ?
            """
            cursor.execute(fallback_query, list(complementary_cats) + [product_id, limit])
            return [dict(r) for r in cursor.fetchall()]

        # Intelligent ranking:
        # 1. Brand match (+100)
        # 2. Preferred category match (+50)
        # 3. Best price
        def score_item(item: dict) -> tuple[int, float]:
            brand_match = 1 if target_brand and target_brand in item.get("name", "").lower() else 0
            cat_match = 1 if preferred_category and item.get("category") == preferred_category else 0
            score = (brand_match * 100) + (cat_match * 50)
            return (-score, item["price"])

        rows.sort(key=score_item)
        return rows[:limit]

    except sqlite3.Error as e:
        logger.error(f"Database error in get_related_products: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Schema evolution helper
# ─────────────────────────────────────────────────────────────────────────────

def ensure_db_schema() -> None:
    """
    Safely check and evolve schema without recreating tables.
    1. Ensures order_items has 'source' column ('customer-selected' vs 'AI-recommended').
    2. Ensures order_items has 'is_ai_recommended' (INTEGER) and 'unit_price' (REAL).
    3. Ensures audit_logs table exists.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check order_items columns
        cursor.execute("PRAGMA table_info(order_items)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "source" not in columns:
            cursor.execute("ALTER TABLE order_items ADD COLUMN source TEXT DEFAULT 'customer-selected'")
            logger.info("Added 'source' column to order_items table.")
        if "is_ai_recommended" not in columns:
            cursor.execute("ALTER TABLE order_items ADD COLUMN is_ai_recommended INTEGER DEFAULT 0")
            logger.info("Added 'is_ai_recommended' column to order_items table.")
        if "unit_price" not in columns:
            cursor.execute("ALTER TABLE order_items ADD COLUMN unit_price REAL DEFAULT 0.0")
            logger.info("Added 'unit_price' column to order_items table.")

        # Backfill existing order_items where values are null or default
        cursor.execute("""
            UPDATE order_items
            SET is_ai_recommended = CASE WHEN source = 'AI-recommended' THEN 1 ELSE 0 END
            WHERE is_ai_recommended IS NULL OR (is_ai_recommended = 0 AND source = 'AI-recommended')
        """)
        cursor.execute("""
            UPDATE order_items
            SET unit_price = (SELECT price FROM products WHERE products.id = order_items.product_id)
            WHERE unit_price IS NULL OR unit_price = 0.0
        """)

        # Ensure audit_logs table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event_type TEXT,
                action TEXT,
                rule_or_tool TEXT,
                details TEXT,
                detail TEXT,
                status TEXT
            )
        """)

        # Ensure campaign_suggestions table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaign_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_type TEXT NOT NULL,
                title TEXT NOT NULL,
                reason TEXT NOT NULL,
                suggested_discount TEXT NOT NULL,
                discount_type TEXT DEFAULT 'fixed',
                discount_amount REAL DEFAULT 0.0,
                target_product_id INTEGER,
                target_product_name TEXT,
                target_audience TEXT,
                objective TEXT,
                evidence TEXT,
                status TEXT DEFAULT 'SUGGESTED',
                created_at TEXT,
                approved_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in ensure_db_schema: {e}")
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Order Management & Fulfillment
# ─────────────────────────────────────────────────────────────────────────────

def create_order(cart: dict, customer_id: int = 1, razorpay_order_id: str = "") -> dict[str, Any]:
    """
    Create a new order in the orders and order_items tables.
    Initial status is 'PENDING'.
    """
    import uuid
    from datetime import datetime

    if not cart:
        raise ValueError("Cannot create an order with an empty cart.")

    total_inr = sum(item["product"]["price"] * item["quantity"] for item in cart.values())
    amount_paise = int(total_inr * 100)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    receipt_id = f"rcpt_{uuid.uuid4().hex[:8]}"

    items_list = list(cart.values())
    product_summary = items_list[0]["product"]["name"]
    if len(items_list) > 1:
        product_summary += f" + {len(items_list) - 1} more item(s)"

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO orders (
                order_id, customer_id, receipt_id, product_name,
                amount_inr, amount_paise, total, status,
                razorpay_order_id, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
            (
                order_id,
                customer_id,
                receipt_id,
                product_summary,
                total_inr,
                amount_paise,
                total_inr,
                razorpay_order_id,
                timestamp,
            ),
        )
        order_db_id = cursor.lastrowid

        # Insert line items with unit_price and is_ai_recommended tracking
        for item in items_list:
            prod = item["product"]
            qty = item["quantity"]
            source = item.get("source", "customer-selected")
            is_ai = 1 if source == "AI-recommended" else 0
            u_price = float(prod.get("price", 0.0))
            cursor.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, source, is_ai_recommended, unit_price)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_db_id, prod["id"], qty, source, is_ai, u_price),
            )

        conn.commit()

        return {
            "id": order_db_id,
            "order_id": order_id,
            "receipt_id": receipt_id,
            "customer_id": customer_id,
            "product_name": product_summary,
            "total": total_inr,
            "amount_inr": total_inr,
            "amount_paise": amount_paise,
            "status": "PENDING",
            "razorpay_order_id": razorpay_order_id,
            "timestamp": timestamp,
            "items": items_list,
        }
    except sqlite3.Error as e:
        logger.error(f"Database error in create_order: {e}")
        raise
    finally:
        if conn:
            conn.close()


def update_order_payment(order_db_id: int, razorpay_order_id: str, status: str = "PAID") -> bool:
    """
    Mark an order as PAID (or other status), associate Razorpay Order ID,
    and deduct purchased quantities from products stock in SQLite.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Update order status
        cursor.execute(
            "UPDATE orders SET status = ?, razorpay_order_id = ? WHERE id = ?",
            (status, razorpay_order_id, order_db_id),
        )

        # Deduct stock for each line item if paid
        if status.upper() == "PAID":
            cursor.execute(
                "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
                (order_db_id,),
            )
            items = cursor.fetchall()
            for item in items:
                cursor.execute(
                    "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )

        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in update_order_payment: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_order_details(order_db_id: int) -> dict[str, Any] | None:
    """
    Retrieve full order details including line items joined with product metadata.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_db_id,))
        order_row = cursor.fetchone()
        if not order_row:
            return None

        order_dict = dict(order_row)

        cursor.execute(
            """
            SELECT oi.id as item_id, oi.product_id, oi.quantity, oi.source,
                   p.name, p.category, 
                   CASE WHEN oi.unit_price > 0 THEN oi.unit_price ELSE p.price END as price,
                   p.description
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
            """,
            (order_db_id,),
        )
        items = [dict(row) for row in cursor.fetchall()]
        order_dict["items"] = items
        return order_dict
    except sqlite3.Error as e:
        logger.error(f"Database error in get_order_details: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_order_by_order_id(order_id_str: str) -> dict[str, Any] | None:
    """Retrieve full order details by the formatted order_id string."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM orders WHERE order_id = ?", (order_id_str,))
        row = cursor.fetchone()
        if row:
            return get_order_details(row["id"])
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error in get_order_by_order_id: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_recent_orders(limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve recent orders ordered by id descending."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error in get_recent_orders: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Merchant Analytics & Inventory Management
# ─────────────────────────────────────────────────────────────────────────────

def get_merchant_analytics() -> dict[str, Any]:
    """
    Calculate comprehensive commerce analytics and AI ROI metrics:
      - Total orders (PAID vs PENDING)
      - Total revenue from PAID orders
      - Revenue split: Customer-Selected vs AI-Recommended
      - Cross-sell conversion rate (% of paid orders with AI suggestions)
      - Total items sold
      - Top AI-recommended products by revenue
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Orders count & Total Revenue
        cursor.execute("SELECT COUNT(*) as total_orders, COALESCE(SUM(amount_inr), 0) as total_revenue FROM orders WHERE status = 'PAID'")
        paid_summary = cursor.fetchone()
        paid_orders_count = paid_summary["total_orders"]
        total_revenue = float(paid_summary["total_revenue"])

        cursor.execute("SELECT COUNT(*) as pending_count FROM orders WHERE status != 'PAID'")
        pending_count = cursor.fetchone()["pending_count"]

        # 2. Total items sold
        cursor.execute("""
            SELECT COALESCE(SUM(oi.quantity), 0) as items_sold
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status = 'PAID'
        """)
        items_sold = cursor.fetchone()["items_sold"]

        # 3. Revenue by Source: Customer-Selected vs AI-Recommended
        cursor.execute("""
            SELECT oi.source, 
                   COALESCE(SUM(oi.quantity * CASE WHEN oi.unit_price > 0 THEN oi.unit_price ELSE p.price END), 0) as revenue, 
                   COALESCE(SUM(oi.quantity), 0) as qty
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status = 'PAID'
            GROUP BY oi.source
        """)
        source_rows = cursor.fetchall()
        source_stats = {
            "customer-selected": {"revenue": 0.0, "qty": 0},
            "AI-recommended": {"revenue": 0.0, "qty": 0},
        }
        for r in source_rows:
            src = r["source"] or "customer-selected"
            source_stats[src] = {"revenue": float(r["revenue"]), "qty": int(r["qty"])}

        cust_rev = source_stats["customer-selected"]["revenue"]
        ai_rev = source_stats["AI-recommended"]["revenue"]

        # Harmonize attribution totals with total_revenue from orders
        if total_revenue > 0 and (cust_rev + ai_rev) > 0:
            calc_sum = cust_rev + ai_rev
            cust_rev = (cust_rev / calc_sum) * total_revenue
            ai_rev = (ai_rev / calc_sum) * total_revenue
        elif total_revenue <= 0 and (cust_rev + ai_rev) > 0:
            total_revenue = cust_rev + ai_rev

        ai_share_pct = (ai_rev / total_revenue * 100) if total_revenue > 0 else 0.0

        # 4. Cross-sell Conversion Rate
        cursor.execute("""
            SELECT COUNT(DISTINCT o.id) as orders_with_ai
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE o.status = 'PAID' AND oi.source = 'AI-recommended'
        """)
        orders_with_ai = cursor.fetchone()["orders_with_ai"]
        conversion_rate = (orders_with_ai / paid_orders_count * 100) if paid_orders_count > 0 else 0.0

        # 5. Top AI-recommended products converted
        cursor.execute("""
            SELECT p.name, p.category, SUM(oi.quantity) as sold_qty, 
                   SUM(oi.quantity * CASE WHEN oi.unit_price > 0 THEN oi.unit_price ELSE p.price END) as revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status = 'PAID' AND (oi.source = 'AI-recommended' OR oi.is_ai_recommended = 1)
            GROUP BY p.id
            ORDER BY revenue DESC
            LIMIT 5
        """)
        top_ai_items = [dict(r) for r in cursor.fetchall()]

        # 6. AI Revenue Breakdown (e.g. Laptop → Wireless Mouse +₹1,299)
        cursor.execute("""
            SELECT 
                p_primary.category as primary_category,
                p_primary.name as primary_name,
                p_upsell.category as upsell_category,
                p_upsell.name as upsell_name,
                SUM(oi_upsell.quantity * CASE WHEN oi_upsell.unit_price > 0 THEN oi_upsell.unit_price ELSE p_upsell.price END) as upsell_revenue,
                SUM(oi_upsell.quantity) as upsell_qty,
                COUNT(DISTINCT o.id) as times_purchased
            FROM order_items oi_upsell
            JOIN orders o ON oi_upsell.order_id = o.id
            JOIN products p_upsell ON oi_upsell.product_id = p_upsell.id
            JOIN order_items oi_primary ON oi_primary.order_id = o.id 
                 AND oi_primary.id != oi_upsell.id 
                 AND (oi_primary.source = 'customer-selected' OR oi_primary.source IS NULL OR oi_primary.is_ai_recommended = 0)
            JOIN products p_primary ON oi_primary.product_id = p_primary.id
            WHERE o.status = 'PAID' AND (oi_upsell.source = 'AI-recommended' OR oi_upsell.is_ai_recommended = 1)
            GROUP BY p_primary.category, p_upsell.name
            ORDER BY upsell_revenue DESC
        """)
        breakdown_rows = cursor.fetchall()
        ai_revenue_breakdown = [dict(r) for r in breakdown_rows]

        # Fallback if no paired customer item exists in that order
        if not ai_revenue_breakdown and ai_rev > 0:
            for item in top_ai_items:
                ai_revenue_breakdown.append({
                    "primary_category": "Direct",
                    "primary_name": "AI Catalog Recommendation",
                    "upsell_category": item.get("category", "Accessory"),
                    "upsell_name": item.get("name", "Product"),
                    "upsell_revenue": float(item.get("revenue", 0.0)),
                    "upsell_qty": int(item.get("sold_qty", 1)),
                    "times_purchased": 1,
                })

        avg_order_value = (total_revenue / paid_orders_count) if paid_orders_count > 0 else 0.0

        return {
            "paid_orders": paid_orders_count,
            "pending_orders": pending_count,
            "total_revenue": total_revenue,
            "customer_selected_revenue": cust_rev,
            "ai_recommended_revenue": ai_rev,
            "ai_assisted_revenue": ai_rev,
            "ai_upsell_revenue": ai_rev,
            "average_order_value": avg_order_value,
            "ai_revenue_share_pct": ai_share_pct,
            "items_sold": items_sold,
            "orders_with_ai_upsell": orders_with_ai,
            "conversion_rate_pct": conversion_rate,
            "top_ai_items": top_ai_items,
            "ai_revenue_breakdown": ai_revenue_breakdown,
        }
    except sqlite3.Error as e:
        logger.error(f"Database error in get_merchant_analytics: {e}")
        return {
            "paid_orders": 0, "pending_orders": 0, "total_revenue": 0.0,
            "customer_selected_revenue": 0.0, "ai_recommended_revenue": 0.0,
            "ai_assisted_revenue": 0.0, "ai_upsell_revenue": 0.0,
            "average_order_value": 0.0, "ai_revenue_share_pct": 0.0, "items_sold": 0,
            "orders_with_ai_upsell": 0, "conversion_rate_pct": 0.0, "top_ai_items": [],
            "ai_revenue_breakdown": [],
        }
    finally:
        if conn:
            conn.close()


def import_catalog_csv(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Validate and import product catalog from a list of dicts in an atomic transaction.
    If a product exists by (name, category), update price, description, and stock.
    Otherwise insert a new product record.

    Parameters
    ----------
    rows : list of dicts with keys: name, category, price, description, stock

    Returns
    -------
    (inserted_count, updated_count)
    """
    if not rows:
        return 0, 0

    conn = None
    inserted_count = 0
    updated_count = 0
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Atomic transaction
        cursor.execute("BEGIN TRANSACTION")

        for row in rows:
            name = str(row["name"]).strip()
            category = str(row["category"]).strip()
            price = float(row["price"])
            description = str(row.get("description", "")).strip()
            stock = int(row["stock"])

            # Check for existing product by name & category
            cursor.execute(
                "SELECT id FROM products WHERE LOWER(name) = LOWER(?) AND LOWER(category) = LOWER(?)",
                (name, category),
            )
            existing = cursor.fetchone()

            if existing:
                prod_id = existing["id"]
                cursor.execute(
                    """
                    UPDATE products
                    SET price = ?, description = ?, stock = ?
                    WHERE id = ?
                    """,
                    (price, description, stock, prod_id),
                )
                updated_count += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO products (name, category, price, description, stock)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, category, price, description, stock),
                )
                inserted_count += 1

        conn.commit()

        # Log audit event
        try:
            from audit import log_event
            log_event(
                event_type="CATALOG_IMPORT",
                action=f"Imported CSV catalog: {inserted_count} new, {updated_count} updated",
                details=f"Total processed rows: {len(rows)}",
                status="SUCCESS",
                rule_or_tool="Merchant Catalog Console",
            )
        except Exception:
            pass

        return {
            "success": True,
            "inserted": inserted_count,
            "updated": updated_count,
        }

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Catalog import transaction failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "inserted": 0,
            "updated": 0,
        }
    finally:
        if conn:
            conn.close()


def restock_product(product_id: int, quantity: int = 10) -> bool:
    """Add stock to a product and log the action."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (quantity, product_id))
        conn.commit()

        cursor.execute("SELECT name, stock FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if row:
            try:
                from audit import log_event
                log_event(
                    event_type="INVENTORY_RESTOCKED",
                    action=f"Restocked {row['name']} (+{quantity} units)",
                    details=f"New Stock: {row['stock']} units",
                    status="SUCCESS",
                    rule_or_tool="Merchant Inventory Console",
                )
            except Exception:
                pass
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in restock_product: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_all_products_admin() -> list[dict[str, Any]]:
    """Retrieve all catalog products ordered by stock ascending for inventory management."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY stock ASC, category ASC, name ASC")
        return [dict(r) for r in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error in get_all_products_admin: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# AI Campaign Agent Data Layer
# ─────────────────────────────────────────────────────────────────────────────

def get_sales_and_catalog_summary() -> dict[str, Any]:
    """
    Summarize actual product sales, category performance, stock levels,
    and cross-sell attachment rates strictly from SQLite tables.
    Returns structured data for the AI Campaign / Offer Agent.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Total paid orders and revenue
        cursor.execute("""
            SELECT count(*) as paid_orders, COALESCE(sum(total), 0.0) as total_revenue
            FROM orders
            WHERE status = 'PAID'
        """)
        totals = dict(cursor.fetchone())

        # 2. Product sales (ranked by units sold)
        cursor.execute("""
            SELECT p.id, p.name, p.category, p.price, p.stock,
                   COALESCE(sum(oi.quantity), 0) as units_sold,
                   COALESCE(sum(oi.quantity * oi.unit_price), 0.0) as revenue
            FROM products p
            LEFT JOIN order_items oi ON p.id = oi.product_id
            LEFT JOIN orders o ON o.id = oi.order_id AND o.status = 'PAID'
            GROUP BY p.id
            ORDER BY units_sold DESC, revenue DESC
        """)
        all_product_sales = [dict(r) for r in cursor.fetchall()]

        # 3. Category sales breakdown
        cursor.execute("""
            SELECT p.category,
                   COALESCE(sum(oi.quantity), 0) as units_sold,
                   COALESCE(sum(oi.quantity * oi.unit_price), 0.0) as revenue
            FROM products p
            LEFT JOIN order_items oi ON p.id = oi.product_id
            LEFT JOIN orders o ON o.id = oi.order_id AND o.status = 'PAID'
            GROUP BY p.category
            ORDER BY units_sold DESC, revenue DESC
        """)
        category_sales = [dict(r) for r in cursor.fetchall()]

        # 4. Low-selling items with high inventory (stock >= 10, units_sold <= 1)
        low_sales_high_stock = [
            p for p in all_product_sales
            if p["stock"] >= 10 and p["units_sold"] <= 1
        ]
        # Sort by stock descending
        low_sales_high_stock.sort(key=lambda x: x["stock"], reverse=True)

        # 5. Attachment rate calculations for key primary categories
        # For orders with Category A (e.g. Laptops), how many also contain Category B (e.g. Laptop Bags, Mouse)?
        attachment_stats = []
        key_pairs = [
            ("Laptops", "Laptop Bags"),
            ("Laptops", "Mouse"),
            ("Laptops", "Headphones"),
            ("Laptops", "Storage"),
            ("Smartphones", "Chargers"),
            ("Smartphones", "Power Banks"),
            ("Smartphones", "Smartwatches"),
            ("Smartphones", "Headphones"),
            ("Tablets", "Keyboards"),
            ("Tablets", "Chargers"),
        ]

        for cat_a, cat_b in key_pairs:
            # Find all paid orders containing cat_a
            cursor.execute("""
                SELECT DISTINCT o.id
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                WHERE o.status = 'PAID' AND (
                    LOWER(p.category) = LOWER(?) OR 
                    LOWER(p.category) = LOWER(?) || 's' OR 
                    LOWER(p.category) || 's' = LOWER(?)
                )
            """, (cat_a, cat_a, cat_a))
            orders_a = [r["id"] for r in cursor.fetchall()]
            total_orders_a = len(orders_a)

            if total_orders_a > 0:
                placeholders = ",".join("?" * total_orders_a)
                cursor.execute(f"""
                    SELECT count(DISTINCT o.id)
                    FROM orders o
                    JOIN order_items oi ON o.id = oi.order_id
                    JOIN products p ON p.id = oi.product_id
                    WHERE o.id IN ({placeholders}) AND (
                        LOWER(p.category) = LOWER(?) OR 
                        LOWER(p.category) = LOWER(?) || 's' OR 
                        LOWER(p.category) || 's' = LOWER(?)
                    )
                """, (*orders_a, cat_b, cat_b, cat_b))
                attached_orders = cursor.fetchone()[0]
                attachment_rate = (attached_orders / total_orders_a) * 100.0
            else:
                attached_orders = 0
                attachment_rate = 0.0

            # Find matching products for cat_b in inventory
            cat_b_prods = [
                p for p in all_product_sales 
                if p["category"].lower() == cat_b.lower() 
                or p["category"].lower() == f"{cat_b.lower()}s" 
                or f"{p['category'].lower()}s" == cat_b.lower()
            ]

            attachment_stats.append({
                "primary_category": cat_a,
                "secondary_category": cat_b,
                "primary_orders_count": total_orders_a,
                "attached_orders_count": attached_orders,
                "attachment_rate_pct": round(attachment_rate, 1),
                "secondary_stock": sum(p["stock"] for p in cat_b_prods),
                "secondary_products": cat_b_prods,
            })

        # Best selling product and category
        top_category = category_sales[0] if category_sales and category_sales[0]["units_sold"] > 0 else None
        top_product = all_product_sales[0] if all_product_sales and all_product_sales[0]["units_sold"] > 0 else None

        return {
            "paid_orders": totals["paid_orders"],
            "total_revenue": totals["total_revenue"],
            "top_category": top_category,
            "top_product": top_product,
            "category_sales": category_sales,
            "product_sales": all_product_sales,
            "low_sales_high_stock": low_sales_high_stock,
            "attachment_stats": attachment_stats,
        }

    except sqlite3.Error as e:
        logger.error(f"Database error in get_sales_and_catalog_summary: {e}")
        return {
            "paid_orders": 0,
            "total_revenue": 0.0,
            "top_category": None,
            "top_product": None,
            "category_sales": [],
            "product_sales": [],
            "low_sales_high_stock": [],
            "attachment_stats": [],
        }
    finally:
        if conn:
            conn.close()


def save_campaign_suggestion(campaign: dict[str, Any]) -> int:
    """Save a proposed campaign to campaign_suggestions table."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        evidence_str = (
            json.dumps(campaign["evidence"])
            if isinstance(campaign.get("evidence"), list)
            else str(campaign.get("evidence", "[]"))
        )

        cursor.execute("""
            INSERT INTO campaign_suggestions (
                campaign_type, title, reason, suggested_discount,
                discount_type, discount_amount, target_product_id,
                target_product_name, target_audience, objective,
                evidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUGGESTED', ?, ?)
        """, (
            campaign.get("campaign_type", "bundle"),
            campaign.get("title", "Campaign Offer"),
            campaign.get("reason", ""),
            campaign.get("suggested_discount", "Special Offer"),
            campaign.get("discount_type", "fixed"),
            float(campaign.get("discount_amount", 0.0)),
            campaign.get("target_product_id"),
            campaign.get("target_product_name", ""),
            campaign.get("target_audience", "All Customers"),
            campaign.get("objective", "Increase sales"),
            evidence_str,
            now_str,
            now_str,
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Database error in save_campaign_suggestion: {e}")
        return 0
    finally:
        if conn:
            conn.close()


def update_campaign_status(campaign_id: int, status: str) -> bool:
    """Update campaign status to APPROVED or REJECTED."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            UPDATE campaign_suggestions
            SET status = ?,
                updated_at = ?,
                approved_at = CASE WHEN ? = 'APPROVED' THEN ? ELSE approved_at END
            WHERE id = ?
        """, (status.upper(), now_str, status.upper(), now_str, campaign_id))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Database error in update_campaign_status: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_latest_campaign_suggestion() -> dict[str, Any] | None:
    """Fetch the latest campaign suggestion."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM campaign_suggestions
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["evidence"] = json.loads(d.get("evidence", "[]"))
        except Exception:
            d["evidence"] = []
        return d
    except sqlite3.Error as e:
        logger.error(f"Database error in get_latest_campaign_suggestion: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_campaign_history(limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve history of all campaign suggestions."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM campaign_suggestions
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["evidence"] = json.loads(d.get("evidence", "[]"))
            except Exception:
                d["evidence"] = []
            result.append(d)
        return result
    except sqlite3.Error as e:
        logger.error(f"Database error in get_campaign_history: {e}")
        return []
    finally:
        if conn:
            conn.close()




