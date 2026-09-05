"""
seed_data.py — TechMart AI Shopping Agent
==========================================
Populates the products table with the official 140-product TechMart catalog.

Usage:
  python seed_data.py          # Seeds or updates catalog
  python seed_data.py --reset  # Clears existing products and seeds clean catalog
"""

import os
import csv
import sqlite3
import sys

DB_PATH = "orders.db"
CSV_PATH = os.path.join(os.path.dirname(__file__), "catalog.csv")


def load_catalog_from_csv() -> list[tuple]:
    """Load all 140 products from catalog.csv."""
    products = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                products.append((
                    int(row["id"]),
                    row["name"].strip(),
                    row["category"].strip(),
                    float(row["price"]),
                    row["description"].strip(),
                    int(row["stock"]),
                ))
    return products


CATALOG_ROWS = load_catalog_from_csv()
# PRODUCTS tuple without ID for backward compatibility
PRODUCTS = [(r[1], r[2], r[3], r[4], r[5]) for r in CATALOG_ROWS]


def seed_products(force: bool = False) -> int:
    """
    Insert catalog products into the SQLite database.
    If force=True, clears existing products first and resets sequence.
    Returns the number of products inserted.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if force:
        cursor.execute("DELETE FROM products")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='products'")
        conn.commit()
    else:
        cursor.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"Products table already contains {count} items.")
            conn.close()
            return count

    rows_to_insert = CATALOG_ROWS if CATALOG_ROWS else load_catalog_from_csv()
    cursor.executemany(
        """
        INSERT INTO products (id, name, category, price, description, stock)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    conn.commit()
    inserted = len(rows_to_insert)
    print(f"Successfully seeded {inserted} products into the catalog.")

    conn.close()
    return inserted


if __name__ == "__main__":
    force_reset = "--reset" in sys.argv or "-r" in sys.argv or True
    count = seed_products(force=force_reset)
    print(f"Total products in catalog: {count}")
