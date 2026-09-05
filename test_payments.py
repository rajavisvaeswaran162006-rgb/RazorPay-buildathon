"""
test_payments.py — Test suite for Order Management & Razorpay Checkout
======================================================================
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import (
    ensure_db_schema,
    get_product,
    create_order,
    update_order_payment,
    get_order_details,
    get_recent_orders,
)
from payments import create_razorpay_order, is_live_key_configured
from audit import log_event, get_recent_logs

def test_order_and_payment():
    ensure_db_schema()

    print("=== TEST 1: Cart Guardrail & Order Creation ===")
    p1 = get_product(1)  # HP 15s
    p2 = get_product(61) # Logitech M185 (Mouse)
    assert p1 is not None and p2 is not None, "Products not found in catalog"

    cart = {
        p1["id"]: {"product": p1, "quantity": 1, "source": "customer-selected"},
        p2["id"]: {"product": p2, "quantity": 1, "source": "AI-recommended"},
    }

    subtotal = p1["price"] + p2["price"]
    budget_limit = 70000.0

    # Guardrail evaluation
    assert subtotal <= budget_limit, f"Budget exceeded: {subtotal} > {budget_limit}"
    assert p1["stock"] >= 1 and p2["stock"] >= 1, "Insufficient stock"

    log_event(
        event_type="GUARDRAIL_CHECK",
        action="Pre-payment safety & budget check",
        details=f"Cart Total: Rs.{subtotal:,.0f}; Budget: Rs.{budget_limit:,.0f}; Stock verified",
        status="PASSED",
        rule_or_tool="Fintech Safety Engine",
    )
    print(f"  + Pre-payment guardrail PASSED: Total Rs. {subtotal:,.0f} <= Rs. {budget_limit:,.0f}")

    # Create order in SQLite
    order = create_order(cart, customer_id=1)
    assert order["id"] is not None
    assert order["status"] == "PENDING"
    assert order["total"] == subtotal
    print(f"  + Order created: {order['order_id']} (DB ID: {order['id']}, Receipt: {order['receipt_id']})")
    print("TEST 1 PASSED!\n")

    print("=== TEST 2: Razorpay Test Order Generation ===")
    rzp_order = create_razorpay_order(order["total"], order["receipt_id"])
    assert rzp_order["id"].startswith("order_")
    assert rzp_order["amount"] == int(subtotal * 100)
    print(f"  + Razorpay order generated: {rzp_order['id']} (Amount: {rzp_order['amount']} paise, Mode: {rzp_order.get('mode')})")
    print("TEST 2 PASSED!\n")

    print("=== TEST 3: Payment Fulfillment & Stock Reduction ===")
    stock1_before = get_product(p1["id"])["stock"]
    stock2_before = get_product(p2["id"])["stock"]

    success = update_order_payment(order["id"], rzp_order["id"], status="PAID")
    assert success, "Failed to update order payment"

    stock1_after = get_product(p1["id"])["stock"]
    stock2_after = get_product(p2["id"])["stock"]

    assert stock1_after == stock1_before - 1, f"Stock1 not decremented: {stock1_before} -> {stock1_after}"
    assert stock2_after == stock2_before - 1, f"Stock2 not decremented: {stock2_before} -> {stock2_after}"

    log_event(
        event_type="PAYMENT_COMPLETED",
        action=f"Order {order['order_id']} paid via Razorpay",
        details=f"Amount: Rs. {subtotal:,.0f}; Razorpay ID: {rzp_order['id']}; Stock decremented",
        status="SUCCESS",
        rule_or_tool="Razorpay Gateway",
    )
    print(f"  + Stock decremented: {p1['name']} ({stock1_before} -> {stock1_after}), {p2['name']} ({stock2_before} -> {stock2_after})")
    print("TEST 3 PASSED!\n")

    print("=== TEST 4: Order Details & History Retrieval ===")
    details = get_order_details(order["id"])
    assert details is not None
    assert details["status"] == "PAID"
    assert len(details["items"]) == 2
    sources = {item["source"] for item in details["items"]}
    assert "customer-selected" in sources and "AI-recommended" in sources
    print(f"  + Order details verified: {details['order_id']} with {len(details['items'])} items")
    for it in details["items"]:
        print(f"    - {it['name']} x{it['quantity']} ({it['source']})")
    print("TEST 4 PASSED!\n")

    print("ALL PAYMENTS & ORDER TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_order_and_payment()
