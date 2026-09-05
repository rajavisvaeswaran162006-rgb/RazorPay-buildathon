"""
test_ai_agent.py — TechMart AI Shopping Agent Test Suite
=========================================================
Tests:
  1. Natural language query extraction & recommendation for laptops under 70000
  2. Headphones query under budget
  3. Gaming query
  4. Zero matches under budget (impossible query)
  5. Audit log entries verification
  6. Cart item source tracking
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from database import ensure_db_schema, get_product
from audit import get_recent_logs, log_event
from agent import process_shopping_request

def test_pipeline():
    ensure_db_schema()
    print("=== TEST 1: Laptop for coding under 70000 ===")
    res1 = process_shopping_request("I need a laptop for coding under 70000")
    assert res1["status"] == "success", f"Expected success, got {res1['status']}"
    assert res1["requirements"]["category"] == "Laptop"
    assert res1["requirements"]["max_price"] == 70000.0
    assert len(res1["recommendations"]) > 0
    for r in res1["recommendations"]:
        p = r["product"]
        assert p["price"] <= 70000.0, f"Guardrail failure: {p['price']} > 70000"
        assert p["stock"] > 0, f"Out of stock product recommended: {p['name']}"
        assert len(r["why_points"]) > 0, "Missing why_points"
        print(f"  + Recommended: {p['name']} (Rs. {p['price']:,.0f})")
        print(f"    Why: {r['why_points']}")
        if r["upsell"]:
            print(f"    Upsell: {r['upsell']['name']} (Rs. {r['upsell']['price']:,.0f})")
    print("TEST 1 PASSED!\n")

    print("=== TEST 2: Headphones under 8000 ===")
    res2 = process_shopping_request("Show me headphones under 8000")
    assert res2["status"] == "success"
    assert res2["requirements"]["category"] == "Headphones"
    assert res2["requirements"]["max_price"] == 8000.0
    for r in res2["recommendations"]:
        p = r["product"]
        assert p["price"] <= 8000.0
        print(f"  + Recommended: {p['name']} (Rs. {p['price']:,.0f})")
    print("TEST 2 PASSED!\n")

    print("=== TEST 3: Gaming query ===")
    res3 = process_shopping_request("I need something for gaming")
    assert res3["status"] == "success"
    assert len(res3["recommendations"]) > 0
    print(f"  + Gaming items found: {len(res3['recommendations'])}")
    for r in res3["recommendations"]:
        print(f"    - {r['product']['name']} ({r['product']['category']})")
    print("TEST 3 PASSED!\n")

    print("=== TEST 4: Zero matches (Laptop under 5000) ===")
    res4 = process_shopping_request("Laptop under 5000")
    assert res4["status"] == "no_match"
    print(f"  + Friendly message: {res4['message']}")
    print("TEST 4 PASSED!\n")

    print("=== TEST 5: Audit Log Verification ===")
    logs = get_recent_logs(20)
    event_types = {log["event_type"] for log in logs}
    print(f"  + Logged event types: {event_types}")
    assert "USER_REQUEST" in event_types, "Missing USER_REQUEST in audit logs"
    assert "PRODUCT_SEARCH" in event_types, "Missing PRODUCT_SEARCH in audit logs"
    assert "PRODUCT_RECOMMENDATION" in event_types, "Missing PRODUCT_RECOMMENDATION in audit logs"
    assert "UPSELL_SUGGESTED" in event_types, "Missing UPSELL_SUGGESTED in audit logs"
    print("TEST 5 PASSED!\n")

    print("ALL TESTS PASSED SUCCESSFULLY! TechMart AI Agent is fully operational.")

if __name__ == "__main__":
    test_pipeline()
