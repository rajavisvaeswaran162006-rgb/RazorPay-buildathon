"""
test_campaign_agent.py -- Automated AI Campaign & Offer Agent Verification
===========================================================================
Tests:
  1. Campaign analysis returns valid structure.
  2. Grounding: Existing products are referenced in recommendations.
  3. Hallucination Guardrail: Invented/fictitious products are rejected.
  4. Discount Bounds Guardrail: Negative discounts & excess discounts are rejected.
  5. Approval Flow: Campaign suggestion can be approved (status -> APPROVED).
  6. Rejection Flow: Campaign suggestion can be rejected (status -> REJECTED).
  7. Audit Logging: Suggestion logged as CAMPAIGN_SUGGESTED.
  8. Audit Logging: Approval/Rejection logged as CAMPAIGN_APPROVED / CAMPAIGN_REJECTED.
  9. Failsafe / Zero Crash: Graceful handling on simulated data scarcity.
  10. Database Integrity: Existing catalog, orders, and order_items preserved.
"""

import sys
from database import (
    ensure_db_schema,
    get_sales_and_catalog_summary,
    save_campaign_suggestion,
    update_campaign_status,
    get_latest_campaign_suggestion,
    get_all_products_admin,
    search_products,
    get_connection,
)
from campaign_agent import (
    analyze_and_suggest_campaign,
    validate_campaign_suggestion,
    approve_campaign,
    reject_campaign,
)
from audit import get_recent_logs

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def test_1_campaign_analysis_structure():
    print("\n=== TEST 1: Campaign Analysis Structure ===")
    ensure_db_schema()
    res = analyze_and_suggest_campaign()
    assert res["status"] == "success", f"Expected status success, got {res['status']}"
    assert "business_insights" in res, "Missing business_insights in result"
    assert "campaign" in res, "Missing campaign in result"

    insights = res["business_insights"]
    assert "top_category" in insights
    assert "best_selling_product" in insights
    assert "opportunity_identified" in insights

    camp = res["campaign"]
    assert "title" in camp
    assert "campaign_type" in camp
    assert "reason" in camp
    assert "suggested_discount" in camp
    assert "evidence" in camp
    assert isinstance(camp["evidence"], list)
    assert len(camp["evidence"]) > 0
    print(f"  + Generated campaign: \"{camp['title']}\" ({camp['campaign_type']})")
    print(f"  + Offer: {camp['suggested_discount']}")
    print(f"  + Evidence count: {len(camp['evidence'])}")
    print("TEST 1 PASSED!")


def test_2_catalog_grounding():
    print("\n=== TEST 2: Product Catalog Grounding ===")
    all_prods = get_all_products_admin()
    catalog_names_lower = {p["name"].strip().lower() for p in all_prods}

    res = analyze_and_suggest_campaign()
    camp = res["campaign"]
    target_prods = camp.get("target_products", [])

    for p in target_prods:
        p_clean = p.strip().lower()
        # Ensure either exact match or contains actual product
        matched = any(p_clean in c or c in p_clean for c in catalog_names_lower)
        assert matched, f"Target product '{p}' is not grounded in SQLite catalog!"
        print(f"  + Verified product '{p}' exists in SQLite catalog")
    print("TEST 2 PASSED!")


def test_3_hallucinated_product_rejected():
    print("\n=== TEST 3: Hallucination Guardrail (Reject Invented Products) ===")
    all_prods = get_all_products_admin()

    fake_campaign = {
        "campaign_type": "bundle",
        "title": "Quantum Laptop + Teleportation Mouse Bundle",
        "reason": "High attachment opportunity for imaginary products",
        "suggested_discount": "₹500 bundle discount",
        "discount_amount": 500.0,
        "discount_type": "fixed",
        "target_products": ["Quantum WarpBook 9000", "Teleportation Wireless Mouse"],
        "evidence": ["Fictitious evidence point 1"],
    }

    is_valid, err_msg = validate_campaign_suggestion(fake_campaign, all_prods)
    assert not is_valid, "Validator accepted hallucinated product!"
    assert "Product Guardrail Blocked" in err_msg, f"Unexpected error message: {err_msg}"
    print(f"  + Correctly blocked hallucinated product: {err_msg}")
    print("TEST 3 PASSED!")


def test_4_invalid_discount_rejected():
    print("\n=== TEST 4: Discount Bounds Guardrail ===")
    all_prods = get_all_products_admin()
    real_prod = all_prods[0]

    # Negative discount
    neg_campaign = {
        "campaign_type": "discount",
        "title": "Negative Discount Campaign",
        "reason": "Testing negative values",
        "suggested_discount": "-10% discount",
        "discount_amount": -10.0,
        "discount_type": "percent",
        "target_products": [real_prod["name"]],
        "evidence": ["Evidence 1"],
    }
    is_valid, err_msg = validate_campaign_suggestion(neg_campaign, all_prods)
    assert not is_valid, "Validator accepted negative discount!"
    print(f"  + Correctly blocked negative discount: {err_msg}")

    # Exorbitant discount (> 50% percent or > product price)
    excess_campaign = {
        "campaign_type": "discount",
        "title": "Excessive 90% Discount",
        "reason": "Testing excessive values",
        "suggested_discount": "90% off everything",
        "discount_amount": 90.0,
        "discount_type": "percent",
        "target_products": [real_prod["name"]],
        "evidence": ["Evidence 1"],
    }
    is_valid, err_msg = validate_campaign_suggestion(excess_campaign, all_prods)
    assert not is_valid, "Validator accepted 90% discount!"
    print(f"  + Correctly blocked excessive percentage discount: {err_msg}")
    print("TEST 4 PASSED!")


def test_5_approval_flow():
    print("\n=== TEST 5: Explicit Human Approval Flow ===")
    res = analyze_and_suggest_campaign()
    camp_id = res["campaign"]["id"]
    assert res["campaign"]["status"] == "SUGGESTED"

    # Approve
    ok = approve_campaign(camp_id)
    assert ok is True

    # Verify DB state
    latest = get_latest_campaign_suggestion()
    assert latest["id"] == camp_id
    assert latest["status"] == "APPROVED"
    assert latest["approved_at"] is not None
    print(f"  + Campaign #{camp_id} successfully approved with approved_at={latest['approved_at']}")
    print("TEST 5 PASSED!")


def test_6_rejection_flow():
    print("\n=== TEST 6: Explicit Human Rejection Flow ===")
    # Save a temporary campaign for rejection test
    temp_camp = {
        "campaign_type": "promotion",
        "title": "Temporary Rejection Test Campaign",
        "reason": "Testing rejection flow",
        "suggested_discount": "₹100 discount",
        "discount_type": "fixed",
        "discount_amount": 100.0,
        "target_products": ["ClickPro Wireless Mouse"],
        "target_audience": "All Shoppers",
        "objective": "Test",
        "evidence": ["✓ Test evidence"],
    }
    cid = save_campaign_suggestion(temp_camp)
    assert cid > 0

    ok = reject_campaign(cid)
    assert ok is True

    latest = get_latest_campaign_suggestion()
    assert latest["id"] == cid
    assert latest["status"] == "REJECTED"
    print(f"  + Campaign #{cid} successfully rejected with status=REJECTED")
    print("TEST 6 PASSED!")


def test_7_8_audit_logging():
    print("\n=== TEST 7 & 8: Audit Logging for Campaigns ===")
    logs = get_recent_logs(limit=20)
    event_types = {l["event_type"] for l in logs}

    assert "CAMPAIGN_ANALYSIS" in event_types, "CAMPAIGN_ANALYSIS not logged"
    assert "CAMPAIGN_SUGGESTED" in event_types, "CAMPAIGN_SUGGESTED not logged"
    assert "CAMPAIGN_APPROVED" in event_types, "CAMPAIGN_APPROVED not logged"
    assert "CAMPAIGN_REJECTED" in event_types, "CAMPAIGN_REJECTED not logged"
    print(f"  + Confirmed audit log event types: {event_types & {'CAMPAIGN_ANALYSIS', 'CAMPAIGN_SUGGESTED', 'CAMPAIGN_APPROVED', 'CAMPAIGN_REJECTED'}}")
    print("TESTS 7 & 8 PASSED!")


def test_9_insufficient_data_safe_fallback():
    print("\n=== TEST 9: Safe Failsafe on Scarcity ===")
    from campaign_agent import generate_deterministic_campaign
    empty_summary = {
        "paid_orders": 0,
        "total_revenue": 0.0,
        "attachment_stats": [],
        "low_sales_high_stock": [],
        "top_product": None,
        "top_category": None,
    }
    all_prods = get_all_products_admin()
    fallback_camp = generate_deterministic_campaign(empty_summary, all_prods)
    assert isinstance(fallback_camp, dict)
    assert "title" in fallback_camp
    assert "evidence" in fallback_camp
    print(f"  + Zero crash fallback generated: \"{fallback_camp['title']}\"")
    print("TEST 9 PASSED!")


def test_10_database_integrity():
    print("\n=== TEST 10: Existing Database Integrity ===")
    all_prods = get_all_products_admin()
    assert len(all_prods) >= 40, f"Expected at least 40 products, got {len(all_prods)}"

    found_laptop = search_products("laptop")
    assert len(found_laptop) > 0, "search_products failed"

    conn = get_connection()
    orders_cnt = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
    items_cnt = conn.execute("SELECT count(*) FROM order_items").fetchone()[0]
    conn.close()

    assert orders_cnt > 0, "Orders table was affected!"
    assert items_cnt > 0, "Order items table was affected!"
    print(f"  + Database integrity confirmed: {len(all_prods)} products, {orders_cnt} orders, {items_cnt} order items intact.")
    print("TEST 10 PASSED!")


if __name__ == "__main__":
    ensure_db_schema()
    test_1_campaign_analysis_structure()
    test_2_catalog_grounding()
    test_3_hallucinated_product_rejected()
    test_4_invalid_discount_rejected()
    test_5_approval_flow()
    test_6_rejection_flow()
    test_7_8_audit_logging()
    test_9_insufficient_data_safe_fallback()
    test_10_database_integrity()
    print("\n🎉 ALL 10 AI CAMPAIGN AGENT TESTS PASSED SUCCESSFULLY!")
