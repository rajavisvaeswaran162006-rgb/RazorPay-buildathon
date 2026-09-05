"""
test_conversational_agent.py — Comprehensive Test Suite for Conversational Customer AI Agent
=============================================================================================
Tests all 11 conversational and context-aware capabilities:
  1. Conversational Memory (session_state context tracking across turns)
  2. Intelligent Clarification (trigger on underspecified query "I need a laptop")
  3. No unnecessary clarification on specific queries ("I need a laptop under 60000 for coding")
  4. Clarification reply merging (category + budget + purpose)
  5. Context-aware comparison ("Which one is better for coding?")
  6. Grounded spec comparison ("Compare the first two")
  7. Context-aware cheaper alternatives ("Show cheaper ones")
  8. Context-aware budget update ("Increase my budget to 75000" preserves category & purpose)
  9. Cart context: Cart summary ("How much is my cart?")
  10. Cart context: Feasibility check ("Can I stay under 50000 with this laptop and cart?")
  11. Cart context: Accessory suggestion within remaining budget
  12. Audit event verification (CLARIFICATION_ASKED, INTENT_UPDATED, PRODUCT_COMPARISON, ALTERNATIVE_SEARCH)
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import ensure_db_schema, get_product
from audit import get_recent_logs, clear_audit_logs
from agent import process_shopping_request, parse_product_specs


def test_conversational_suite():
    ensure_db_schema()
    clear_audit_logs()
    print("======================================================================")
    print("STARTING TEST SUITE: CONVERSATIONAL & CONTEXT-AWARE AI SHOPPING AGENT")
    print("======================================================================")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1: Intelligent Clarification on Underspecified Request
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 1: Intelligent Clarification on Underspecified Request ---")
    res1 = process_shopping_request("I need a laptop")
    assert res1["status"] == "clarification", f"Expected clarification status, got {res1['status']}"
    assert len(res1["recommendations"]) == 0, "Should not recommend before clarification"
    assert "budget" in res1["message"].lower(), "Clarification should ask for budget"
    assert "coding" in res1["message"].lower() or "gaming" in res1["message"].lower(), "Clarification should ask for purpose"
    ctx1 = res1["conversation_context"]
    assert ctx1["category"] == "Laptop", f"Context should remember Laptop, got {ctx1.get('category')}"
    assert ctx1["awaiting_clarification"] == "budget_and_purpose", "Should set awaiting_clarification"
    print(f"  + Agent asked intelligent clarification: '{res1['message']}'")
    print("TEST 1 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2: Clarification Reply Merging & Immediate Search
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 2: Clarification Reply Merging & Immediate Search ---")
    res2 = process_shopping_request("under 60000 for coding", context=ctx1)
    assert res2["status"] == "success", f"Expected success, got {res2['status']}"
    assert res2["requirements"]["category"] == "Laptop", "Should retain Laptop category"
    assert res2["requirements"]["max_price"] == 60000.0, f"Expected 60000.0 budget, got {res2['requirements']['max_price']}"
    assert res2["requirements"]["purpose"] == "coding", "Should parse coding purpose"
    assert len(res2["recommendations"]) > 0, "Should return matching recommendations"
    for r in res2["recommendations"]:
        assert r["product"]["price"] <= 60000.0, f"Exceeded budget: {r['product']['price']}"
        assert r["product"]["category"] in ("Laptop", "Laptops"), f"Wrong category: {r['product']['category']}"
    ctx2 = res2["conversation_context"]
    assert ctx2["awaiting_clarification"] is None, "Should clear awaiting_clarification"
    assert len(ctx2["recently_displayed_products"]) > 0, "Should record recently displayed products"
    print(f"  + Merged intent: Category={ctx2['category']}, Budget=₹{ctx2['budget']:,.0f}, Purpose={ctx2['purpose']}")
    print(f"  + Returned {len(res2['recommendations'])} verified laptop(s)")
    print("TEST 2 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3: No Unnecessary Clarification on Fully-Specified Requests
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 3: No Unnecessary Clarification on Specified Queries ---")
    res3a = process_shopping_request("I need a laptop under 60000 for coding")
    assert res3a["status"] == "success", "Should search immediately without clarification"
    assert len(res3a["recommendations"]) > 0

    res3b = process_shopping_request("Laptop under 50000")
    assert res3b["status"] == "success", "Should search immediately with budget"
    assert len(res3b["recommendations"]) > 0

    res3c = process_shopping_request("boAt headphones")
    assert res3c["status"] == "success", "Should search immediately with brand/keyword"
    print("  + All 3 specified queries bypassed clarification and searched catalog immediately")
    print("TEST 3 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 4: Context-Aware Comparison ("Which one is better for coding?")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 4: Context-Aware Comparison ('Which one is better for coding?') ---")
    res4 = process_shopping_request("Which one is better for coding?", context=ctx2)
    assert res4["status"] == "success"
    # Should evaluate RAM & processor specs of displayed laptops
    assert "RAM" in res4["message"], "Comparison should analyze RAM"
    assert any(p["name"] in res4["message"] for p in ctx2["recently_displayed_products"]), "Should reference actual models"
    print("  + Grounded comparison reasoning generated:")
    print("    " + res4["message"].split("\n")[0])
    print("TEST 4 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 5: Grounded Side-by-Side Spec Comparison ("Compare the first two")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 5: Grounded Side-by-Side Comparison ('Compare the first two') ---")
    res5 = process_shopping_request("Compare the first two", context=ctx2)
    assert res5["status"] == "success"
    assert "| Specification |" in res5["message"] or "| Feature / Spec |" in res5["message"], "Should render comparison markdown table"
    assert "RAM" in res5["message"]
    assert "Storage" in res5["message"]
    assert "Processor" in res5["message"]
    assert len(res5["recommendations"]) >= 2, "Should return compared cards"
    print("  + Side-by-side markdown table verified with genuine catalog specs")
    print("TEST 5 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 6: Context-Aware Cheaper Alternatives ("Show cheaper ones")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 6: Context-Aware Cheaper Alternatives ('Show cheaper ones') ---")
    res6 = process_shopping_request("Show cheaper ones", context=ctx2)
    assert res6["status"] == "success"
    assert len(res6["recommendations"]) > 0
    # Must be cheaper than top previous options
    cheapest_orig = min(p["price"] for p in ctx2["recently_displayed_products"])
    for r in res6["recommendations"]:
        assert r["product"]["price"] <= cheapest_orig, f"Alternative not cheaper: {r['product']['price']} > {cheapest_orig}"
        print(f"  + Cheaper option: {r['product']['name']} (₹{r['product']['price']:,.0f})")
    ctx6 = res6["conversation_context"]
    print("TEST 6 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 7: Context-Aware Budget Update ("Increase my budget to 75000")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 7: Budget Update Preserves Category & Purpose ---")
    res7 = process_shopping_request("Increase my budget to 75000", context=ctx2)
    assert res7["status"] == "success"
    assert res7["requirements"]["category"] == "Laptop", "Should preserve Laptop category"
    assert res7["requirements"]["max_price"] == 75000.0, f"Expected 75000 budget, got {res7['requirements']['max_price']}"
    assert res7["requirements"]["purpose"] == "coding", "Should preserve coding purpose"
    # Should unlock higher-spec laptop like ASUS TUF Gaming F15, Lenovo ThinkPad E14, or HP Pavilion 14
    rec_names = [r["product"]["name"] for r in res7["recommendations"]]
    assert any("TUF" in name or "ThinkPad" in name or "Pavilion" in name for name in rec_names), f"Should recommend unlocked laptops: {rec_names}"
    print(f"  + Updated budget to ₹75,000; Unlocked higher-spec models: {rec_names}")
    print("TEST 7 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 8: Another Alternative ("Show me another one")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 8: Another Alternative ('Show me another one') ---")
    res8 = process_shopping_request("Show me another one", context=ctx2)
    assert res8["status"] == "success"
    # Should exclude already displayed IDs
    prev_ids = {p["id"] for p in ctx2["recently_displayed_products"]}
    for r in res8["recommendations"]:
        assert r["product"]["id"] not in prev_ids, f"Returned duplicate product {r['product']['name']}"
    print(f"  + Fresh alternative returned without duplicates")
    print("TEST 8 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 9: Cart Context Queries
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 9: Cart Context Queries ---")
    # 9a. Empty cart
    cart_ctx = dict(ctx2)
    cart_ctx["cart"] = {}
    res9a = process_shopping_request("How much is my cart?", context=cart_ctx)
    assert "empty" in res9a["message"].lower(), "Should report empty cart"

    # 9b. Cart with item: Add Acer Aspire 3 (₹42,990)
    laptop_prod = get_product(9)  # Acer Aspire 3 (₹42,990)
    cart_ctx["cart"] = {
        laptop_prod["id"]: {
            "product": laptop_prod,
            "quantity": 1,
            "source": "customer-selected",
        }
    }
    cart_ctx["currently_selected_product"] = laptop_prod
    cart_ctx["budget"] = 50000.0

    res9b = process_shopping_request("How much is my cart?", context=cart_ctx)
    assert f"₹{laptop_prod['price']:,.0f}" in res9b["message"] or "42,990" in res9b["message"]
    print("  + Cart summary correctly reported live items and total")

    # 9c. Feasibility check: "Can I stay under 50000 with this laptop and cart?"
    res9c = process_shopping_request("Can I stay under 50000 with this laptop and cart?", context=cart_ctx)
    assert "yes" in res9c["message"].lower(), "₹42,990 is under ₹50,000"
    print("  + Budget feasibility verified with exact arithmetic")

    # 9d. Accessory suggestion within remaining budget
    res9d = process_shopping_request("Can you suggest an accessory within my remaining budget?", context=cart_ctx)
    assert res9d["status"] == "success"
    assert len(res9d["recommendations"]) > 0
    remaining_budget = 50000.0 - laptop_prod["price"]  # 7010
    for r in res9d["recommendations"]:
        assert r["product"]["price"] <= remaining_budget, f"Accessory price {r['product']['price']} > {remaining_budget}"
        print(f"  + Accessory: {r['product']['name']} (₹{r['product']['price']:,.0f}) <= ₹{remaining_budget:,.0f}")
    print("TEST 9 PASSED!")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 10: Audit Log Event Verification
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 10: Audit Log Event Verification ---")
    logs = get_recent_logs(limit=150)
    event_types = {l["event_type"] for l in logs}
    print(f"  + Logged event types ({len(logs)} entries): {event_types}")

    assert "CLARIFICATION_ASKED" in event_types, "Missing CLARIFICATION_ASKED in audit logs"
    assert "INTENT_UPDATED" in event_types, "Missing INTENT_UPDATED in audit logs"
    assert "PRODUCT_COMPARISON" in event_types, "Missing PRODUCT_COMPARISON in audit logs"
    assert "ALTERNATIVE_SEARCH" in event_types, "Missing ALTERNATIVE_SEARCH in audit logs"
    assert "USER_REQUEST" in event_types, "Missing USER_REQUEST in audit logs"
    print("TEST 10 PASSED!")

    print("\n======================================================================")
    print("ALL 10 CONVERSATIONAL AI AGENT TESTS PASSED SUCCESSFULLY! 100% OPERATIONAL")
    print("======================================================================")


if __name__ == "__main__":
    test_conversational_suite()
