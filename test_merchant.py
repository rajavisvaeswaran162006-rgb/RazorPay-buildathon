"""
test_merchant.py — Test suite for Merchant Commerce & AI Analytics Dashboard
===========================================================================
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import (
    get_merchant_analytics,
    restock_product,
    get_all_products_admin,
    get_product,
)

def test_merchant_operations():
    print("=== TEST 1: Merchant Analytics Metrics ===")
    analytics = get_merchant_analytics()
    print(f"  + Paid Orders: {analytics['paid_orders']}")
    print(f"  + Total Revenue: Rs. {analytics['total_revenue']:,.0f}")
    print(f"  + Customer-Selected Rev: Rs. {analytics['customer_selected_revenue']:,.0f}")
    print(f"  + AI-Recommended Rev: Rs. {analytics['ai_recommended_revenue']:,.0f} ({analytics['ai_revenue_share_pct']:.1f}% of total)")
    print(f"  + Cross-sell Conversion Rate: {analytics['conversion_rate_pct']:.1f}%")
    print(f"  + Items Sold: {analytics['items_sold']}")
    print(f"  + Top AI Items: {len(analytics['top_ai_items'])}")
    assert "total_revenue" in analytics
    assert "ai_recommended_revenue" in analytics
    print("TEST 1 PASSED!\n")

    print("=== TEST 2: Inventory Admin Listing ===")
    prods = get_all_products_admin()
    assert len(prods) == 140, f"Expected 140 products, got {len(prods)}"
    print(f"  + Retrieved {len(prods)} products for inventory management")
    print(f"  + Lowest stock item: {prods[0]['name']} (Stock: {prods[0]['stock']})")
    print("TEST 2 PASSED!\n")

    print("=== TEST 3: Restock Operation ===")
    p1 = get_product(1)
    stock_before = p1["stock"]
    success = restock_product(1, quantity=10)
    assert success, "Restock failed"
    stock_after = get_product(1)["stock"]
    assert stock_after == stock_before + 10, f"Stock mismatch: {stock_before} -> {stock_after}"
    print(f"  + Restocked {p1['name']}: {stock_before} -> {stock_after} (+10)")
    print("TEST 3 PASSED!\n")

    print("ALL MERCHANT DASHBOARD TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_merchant_operations()
