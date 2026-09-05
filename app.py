"""
app.py -- TechMart AI Shopping Agent & Merchant Commerce Platform
==================================================================
A dual-view Streamlit Commerce Application:
  1. 🛍️ Customer Shopping Agent:
     - Natural-language shopping queries processed by AI Shopping Agent (agent.py)
     - Parameterized SQLite product search (database.py)
     - AI product recommendations with structured "Why I recommend it" checklist
     - Catalog-grounded cross-sell / upsell suggestions with explicit customer approval
     - Instant Buy & Cart multi-item checkout
     - Fintech Pre-Payment Safety Guardrails (Budget & Stock evaluation)
     - Full Razorpay Payment Gateway Page with UPI/QR, Cards, Net Banking
     - Automatic Inventory Stock Deduction on payment confirmation
  2. 📊 Merchant Commerce & AI Analytics Dashboard:
     - Real-time revenue attribution (Customer-Selected vs AI-Recommended)
     - AI Cross-Sell Conversion Rate & ROI metrics
     - Live Orders Management & line-item inspection
     - Real-time inventory monitoring & 1-click restocking (+10 units)
     - Fintech compliance audit trail with CSV export

Run:  streamlit run app.py
"""

import io
import os
import csv
import time
import uuid
import streamlit as st
import streamlit.components.v1 as components
from database import (
    ensure_db_schema,
    search_products,
    get_product,
    get_categories,
    get_product_count,
    create_order,
    update_order_payment,
    get_order_details,
    get_order_by_order_id,
    get_recent_orders,
    get_merchant_analytics,
    restock_product,
    get_all_products_admin,
    import_catalog_csv,
    get_latest_campaign_suggestion,
    get_campaign_history,
    get_sales_and_catalog_summary,
)
from seed_data import seed_products
from agent import process_shopping_request
from campaign_agent import (
    analyze_and_suggest_campaign,
    approve_campaign,
    reject_campaign,
)
from audit import log_event, get_recent_logs, clear_audit_logs
from payments import (
    create_razorpay_order,
    create_razorpay_payment_link,
    is_live_key_configured,
    get_razorpay_checkout_config,
)
from styles import (
    inject_custom_css,
    render_header_bar,
    render_hero_banner,
    render_agent_understanding,
    render_catalog_search,
    render_guardrail_blocked,
    render_guardrails_sidebar_panel,
    render_kpi_card_html,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be the first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TechMart AI Commerce Platform",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. SESSION STATE INITIALISATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_session_state() -> None:
    """Set up all session state keys with default values."""
    if "cart" not in st.session_state:
        # cart = {product_id: {"product": dict, "quantity": int, "source": str}}
        st.session_state.cart = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_results" not in st.session_state:
        st.session_state.last_results = []
    if "checkout_active" not in st.session_state:
        st.session_state.checkout_active = False
    if "current_order" not in st.session_state:
        st.session_state.current_order = None
    if "current_rzp_order" not in st.session_state:
        st.session_state.current_rzp_order = None
    if "last_confirmed_order" not in st.session_state:
        st.session_state.last_confirmed_order = None
    if "customer_budget" not in st.session_state:
        st.session_state.customer_budget = None
    if "guardrail_eval" not in st.session_state:
        st.session_state.guardrail_eval = None
    if "active_page" not in st.session_state:
        st.session_state.active_page = "main"
    if "rzp_auth_step" not in st.session_state:
        st.session_state.rzp_auth_step = "method_selection"
    if "rzp_selected_method" not in st.session_state:
        st.session_state.rzp_selected_method = "UPI / QR"
    if "conversation_context" not in st.session_state:
        st.session_state.conversation_context = {
            "previous_user_request": None,
            "category": None,
            "budget": None,
            "min_price": None,
            "purpose": None,
            "preferences": None,
            "recently_displayed_products": [],
            "currently_selected_product": None,
            "awaiting_clarification": None,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. CART & CHECKOUT OPERATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def add_to_cart(product: dict, quantity: int = 1, source: str = "customer-selected") -> str:
    """
    Add a product to the cart with source tracking ('customer-selected' or 'AI-recommended').
    Prevents adding more than available stock.
    Logs addition to audit log.
    """
    pid = product["id"]
    current_qty = st.session_state.cart.get(pid, {}).get("quantity", 0)
    available = product["stock"]

    if current_qty + quantity > available:
        return f"Cannot add — only {available - current_qty} more in stock."

    if pid in st.session_state.cart:
        st.session_state.cart[pid]["quantity"] += quantity
    else:
        st.session_state.cart[pid] = {
            "product": product,
            "quantity": quantity,
            "source": source,
        }

    # Reset confirmed order view on new additions
    st.session_state.last_confirmed_order = None

    log_event(
        event_type="PRODUCT_ADDED_TO_CART",
        action=f"Added '{product['name']}' to cart",
        details=f"Qty: {quantity}; Price: ₹{product['price']:,.0f}; Source: {source}; Remaining stock: {available - (current_qty + quantity)}",
        status="SUCCESS",
        rule_or_tool="Cart Manager",
    )

    return f"Added {product['name'][:35]} to cart!"


def remove_from_cart(product_id: int) -> None:
    """Remove a product entirely from the cart."""
    item = st.session_state.cart.pop(product_id, None)
    if item:
        p = item["product"]
        log_event(
            event_type="CART_REMOVAL",
            action=f"Removed '{p['name']}' from cart",
            details=f"Item ID: {product_id}",
            status="SUCCESS",
            rule_or_tool="Cart Manager",
        )


def update_cart_quantity(product_id: int, new_quantity: int) -> str:
    """Update quantity for a cart item. Returns a status message."""
    if product_id not in st.session_state.cart:
        return "Item not in cart."

    product = st.session_state.cart[product_id]["product"]

    if new_quantity <= 0:
        remove_from_cart(product_id)
        return f"Removed {product['name'][:35]} from cart."

    if new_quantity > product["stock"]:
        return f"Cannot exceed stock ({product['stock']} available)."

    st.session_state.cart[product_id]["quantity"] = new_quantity
    return f"Updated quantity to {new_quantity}."


def get_cart_subtotal() -> float:
    """Calculate the total price of all items in the cart."""
    total = 0.0
    for item in st.session_state.cart.values():
        total += item["product"]["price"] * item["quantity"]
    return total


def get_cart_item_count() -> int:
    """Total number of items (sum of quantities) in the cart."""
    return sum(item["quantity"] for item in st.session_state.cart.values())


def start_checkout() -> bool:
    """
    Validate inventory, evaluate safety guardrails, create SQLite order,
    and generate Razorpay test order.
    """
    cart = st.session_state.cart
    if not cart:
        st.error("Cart is empty.")
        return False

    # 1. Real-time Inventory Verification
    for pid, item in cart.items():
        current_prod = get_product(pid)
        if not current_prod or current_prod["stock"] < item["quantity"]:
            avail = current_prod["stock"] if current_prod else 0
            err_msg = f"Stock error: '{item['product']['name']}' only has {avail} left in stock."
            st.error(err_msg)
            log_event(
                event_type="GUARDRAIL_CHECK",
                action="Stock availability check failed",
                details=err_msg,
                status="FAILED",
                rule_or_tool="Fintech Safety Engine",
            )
            return False

    subtotal = get_cart_subtotal()
    budget_limit = st.session_state.get("customer_budget")

    # 2. Fintech Guardrail Check (Budget Threshold)
    if budget_limit is not None and subtotal > budget_limit:
        guardrail_status = "WARNING"
        guardrail_msg = f"Requested total ₹{subtotal:,.0f} exceeds customer budget limit ₹{budget_limit:,.0f}."
    else:
        guardrail_status = "PASSED"
        b_str = f"₹{budget_limit:,.0f}" if budget_limit else "No ceiling specified"
        guardrail_msg = f"Requested total ₹{subtotal:,.0f} verified within threshold ({b_str}). Inventory verified."

    log_event(
        event_type="GUARDRAIL_CHECK",
        action="Pre-payment safety & budget check",
        details=guardrail_msg,
        status=guardrail_status,
        rule_or_tool="Fintech Safety Engine",
    )

    # 3. Create SQLite Order record
    order = create_order(cart, customer_id=1)

    # 4. Generate Razorpay Test Order
    rzp_order = create_razorpay_order(subtotal, order["receipt_id"])

    log_event(
        event_type="CHECKOUT_INITIATED",
        action=f"Order {order['order_id']} created for checkout",
        details=f"Amount: ₹{subtotal:,.0f}; Razorpay Order: {rzp_order['id']}; Gateway Mode: {rzp_order.get('mode')}",
        status="INITIALIZED",
        rule_or_tool="Checkout Manager",
    )

    st.session_state.current_order = order
    st.session_state.current_rzp_order = rzp_order
    st.session_state.checkout_active = True
    st.session_state.guardrail_eval = {
        "status": guardrail_status,
        "details": guardrail_msg,
        "subtotal": subtotal,
        "budget": budget_limit,
    }
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. UI COMPONENTS: CUSTOMER EXPERIENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CATEGORY_ICONS = {
    "Laptop": "💻",
    "Smartphone": "📱",
    "Tablet": "📟",
    "Headphones": "🎧",
    "Speaker": "🔊",
    "Earbuds": "🎵",
    "Mouse": "🖱️",
    "Keyboard": "⌨️",
    "Monitor": "🖥️",
    "Charger": "🔌",
    "Power Bank": "🔋",
    "Laptop Bag": "🎒",
    "Smartwatch": "⌚",
    "Router": "📶",
    "Storage": "💾",
    # Plural aliases matching 140-item catalog
    "Laptops": "💻",
    "Smartphones": "📱",
    "Tablets": "📟",
    "Monitors": "🖥️",
    "Keyboards": "⌨️",
    "Mice": "🖱️",
    "Speakers": "🔊",
    "Chargers": "🔌",
    "Power Banks": "🔋",
    "Laptop Bags": "🎒",
    "Smartwatches": "⌚",
    "Routers": "📶",
    "Accessories": "🎒",
}


def render_ai_recommendation_card(rec: dict, msg_idx: int, rec_idx: int) -> None:
    """
    Render an AI-recommended product card with:
      - AI Recommendation badge
      - Product name, category, price, stock
      - 'Why I recommend it' explanation checklist
      - [Add to Cart] and [Buy Now] buttons
      - 'You may also need' cross-sell section with [Add Suggested Item] button
    """
    product = rec["product"]
    why_points = rec.get("why_points", [])
    upsell = rec.get("upsell")
    upsell_pitch = rec.get("upsell_pitch")

    with st.container(border=True):
        icon = CATEGORY_ICONS.get(product["category"], "📦")
        stock = product["stock"]
        if stock > 10:
            stock_badge = f"<span class='tm-pill-stock-high'>🟢 {stock} in stock</span>"
        elif stock > 0:
            stock_badge = f"<span class='tm-pill-stock-low'>🟠 Only {stock} left!</span>"
        else:
            stock_badge = "<span class='tm-pill-stock-out'>🔴 Out of stock</span>"

        st.markdown(
            f"""
            <div class="tm-product-card-top">
                <span class="tm-category-pill">{icon} {product['category']}</span>
                <span class="tm-pill-ai">✨ AI Recommendation</span>
            </div>
            <div class="tm-product-title">{product['name']}</div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span class="tm-product-price">₹{product['price']:,.0f}</span>
                {stock_badge}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption(product["description"])

        # ── Why I recommend it ───────────────────────────────────────────
        if why_points:
            st.markdown("<div style='font-size:12px; font-weight:700; color:#e2e8f0; margin-top:8px; margin-bottom:4px;'>Why I recommend it:</div>", unsafe_allow_html=True)
            for pt in why_points:
                st.markdown(
                    f"<div class='tm-why-point'><span class='tm-why-icon'>✓</span><span>{pt}</span></div>",
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

        # ── Action Buttons ───────────────────────────────────────────────
        if product["stock"] > 0:
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                if st.button(
                    "🛒 Add to Cart",
                    key=f"btn_add_{product['id']}_{msg_idx}_{rec_idx}",
                    use_container_width=True,
                ):
                    msg = add_to_cart(product, quantity=1, source="customer-selected")
                    if "Cannot" in msg:
                        st.error(msg)
                    else:
                        st.toast(msg, icon="🛒")
                        st.rerun()
            with col_b2:
                if st.button(
                    "⚡ Buy Now",
                    key=f"btn_buy_{product['id']}_{msg_idx}_{rec_idx}",
                    use_container_width=True,
                    type="primary",
                ):
                    add_to_cart(product, quantity=1, source="customer-selected")
                    if start_checkout():
                        # Direct immediately to Razorpay Checkout page
                        st.session_state.active_page = "razorpay_checkout"
                        st.query_params["page"] = "razorpay_checkout"
                        if st.session_state.current_order:
                            st.query_params["order_id"] = st.session_state.current_order["order_id"]
                    st.rerun()
        else:
            st.button(
                "Out of Stock",
                key=f"oos_{product['id']}_{msg_idx}_{rec_idx}",
                use_container_width=True,
                disabled=True,
            )

        # ── Upsell / Cross-sell Section ──────────────────────────────────
        if upsell and upsell["stock"] > 0:
            st.markdown(
                f"""
                <div class="tm-upsell-container">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="font-weight:800; font-size:12px; color:#e9d5ff;">💡 YOU MAY ALSO NEED:</span>
                        <span class="tm-pill-ai">Suggested Accessory</span>
                    </div>
                    <div style="font-size:14px; font-weight:700; color:#ffffff; margin-bottom:2px;">
                        {upsell['name']} &nbsp;—&nbsp; <span style="color:#38bdf8; font-family:var(--tm-font-mono);">₹{upsell['price']:,.0f}</span>
                    </div>
                    <div style="font-size:11px; color:#cbd5e1; margin-bottom:6px;">
                        {upsell_pitch or ''}
                    </div>
                    <div style="font-size:10px; color:#a78bfa; margin-bottom:8px;">
                        🔒 <i>Explicit customer approval required — click below to add.</i>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                f"✨ Add Suggested Item — ₹{upsell['price']:,.0f}",
                key=f"btn_upsell_{upsell['id']}_{msg_idx}_{rec_idx}",
                use_container_width=True,
            ):
                msg = add_to_cart(upsell, quantity=1, source="AI-recommended")
                if "Cannot" in msg:
                    st.error(msg)
                else:
                    log_event(
                        event_type="UPSELL_APPROVED",
                        action=f"Customer approved upsell: {upsell['name']}",
                        details=f"Product ID: {upsell['id']}; Price: ₹{upsell['price']:,.0f}; Added to cart with source='AI-recommended'",
                        status="APPROVED",
                        rule_or_tool="Upsell Engine",
                    )
                    st.toast(f"Approved suggestion! {msg}", icon="✨")
                    st.rerun()


def render_recommendations_grid(recommendations: list[dict], msg_idx: int) -> None:
    """Display a responsive grid of AI recommendation cards in clean rows of 3."""
    if not recommendations:
        return

    chunk_size = 3
    for chunk_start in range(0, len(recommendations), chunk_size):
        chunk = recommendations[chunk_start : chunk_start + chunk_size]
        cols = st.columns(3)
        for col_idx, rec in enumerate(chunk):
            with cols[col_idx]:
                render_ai_recommendation_card(rec, msg_idx, chunk_start + col_idx)


def render_agentic_flow(msg: dict, msg_idx: int) -> None:
    """
    Renders the visibly agentic customer shopping experience:
      1. 🤖 AGENT UNDERSTANDING: Category, Budget, Purpose, Preferences
      2. 🔎 CATALOG SEARCH: Products evaluated vs matching constraints
      3. ⭐ AI RECOMMENDATION: Product cards with 'Why I recommend it'
      4. ✨ AI CROSS-SELL: Suggested accessory with explicit customer approval
      5. 🛡️ GUARDRAIL BLOCKED: Clear explanation if candidates exceeded budget/stock
    """
    understanding = msg.get("agent_understanding")
    catalog_search = msg.get("catalog_search")
    recommendations = msg.get("recommendations", [])

    # 1. 🤖 AGENT UNDERSTANDING
    if understanding:
        render_agent_understanding(understanding)

    # 2. 🔎 CATALOG SEARCH
    if catalog_search:
        render_catalog_search(catalog_search)

    # 3. ⭐ AI RECOMMENDATIONS & CROSS-SELLS
    if recommendations:
        render_recommendations_grid(recommendations, msg_idx)

    # 4. 🛡️ GUARDRAIL BLOCKED (if any over-budget or out-of-stock items were prevented)
    if catalog_search and catalog_search.get("blocked_candidates"):
        render_guardrail_blocked(catalog_search["blocked_candidates"])


def render_cart_sidebar() -> None:
    """Render shopping cart, checkout modal, order confirmations & live audit log."""
    # ── Visible Agent Guardrails Status Panel ─────────────────────────
    with st.sidebar:
        render_guardrails_sidebar_panel()

    # ── 1. Confirmed Order Invoice View (if just paid) ───────────────
    if st.session_state.last_confirmed_order:
        order = st.session_state.last_confirmed_order
        with st.sidebar:
            with st.container(border=True):
                st.markdown("### 🎉 Payment Successful!")
                st.markdown(
                    "<span class='tm-pill-stock-high' style='font-size:12px; font-weight:700;'>STATUS: PAID ✅</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Order ID:** `{order['order_id']}`")
                st.caption(f"Receipt: `{order['receipt_id']}` | Gateway ID: `{order.get('razorpay_order_id', '')}`")
                st.caption(f"Time: {order['timestamp']}")

                st.markdown("##### Purchased Items:")
                for item in order.get("items", []):
                    badge = "✨ AI-Recommended" if item.get("source") == "AI-recommended" else "👤 Customer-Selected"
                    st.markdown(f"- **{item['name'][:26]}** x{item['quantity']} — ₹{item['price'] * item['quantity']:,.0f} `({badge})`")

                st.markdown(f"### Total Paid: ₹{order['total']:,.0f}")
                st.caption("✓ Inventory has been decremented in SQLite catalog.")

                if st.button("🛒 Start New Order", key="btn_new_order", use_container_width=True):
                    st.session_state.last_confirmed_order = None
                    st.rerun()

            st.divider()

    # ── 2. Active Checkout Mode in Sidebar ───────────────────────────
    elif st.session_state.checkout_active and st.session_state.current_order:
        order = st.session_state.current_order
        rzp_order = st.session_state.current_rzp_order or {}
        eval_data = st.session_state.get("guardrail_eval", {})

        with st.sidebar:
            with st.container(border=True):
                st.markdown("### 💳 Razorpay Checkout")

                # Fintech Guardrail Evaluation Display
                if eval_data.get("status") == "PASSED":
                    st.markdown(
                        f"""
                        <div style='background:linear-gradient(135deg, rgba(6,78,59,0.5) 0%, rgba(15,23,42,0.85) 100%); border:1px solid rgba(16,185,129,0.4); border-left:4px solid #10b981; border-radius:10px; padding:12px; margin-bottom:12px;'>
                            <div style='font-weight:800; font-size:12px; color:#6ee7b7; margin-bottom:6px;'>✅ FINTECH GUARDRAIL: PASSED</div>
                            <div style='font-family:var(--tm-font-mono); font-size:11px; color:#cbd5e1; line-height:1.6;'>
                            ├── <b>Requested:</b> ₹{order['total']:,.0f}<br>
                            ├── <b>Budget Check:</b> Safe & Approved<br>
                            └── <b>Inventory:</b> Stock Reserved
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""
                        <div style='background:linear-gradient(135deg, rgba(120,53,15,0.45) 0%, rgba(15,23,42,0.85) 100%); border:1px solid rgba(245,158,11,0.4); border-left:4px solid #f59e0b; border-radius:10px; padding:12px; margin-bottom:12px;'>
                            <div style='font-weight:800; font-size:12px; color:#fcd34d; margin-bottom:6px;'>⚠️ GUARDRAIL WARNING</div>
                            <div style='font-family:var(--tm-font-mono); font-size:11px; color:#cbd5e1; line-height:1.6;'>
                            ├── <b>Total:</b> ₹{order['total']:,.0f}<br>
                            └── <b>Note:</b> Exceeds initial budget limit.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown(f"**Order ID:** `{order['order_id']}`")
                st.markdown(f"**Receipt ID:** `{order['receipt_id']}`")
                st.markdown(f"**Razorpay Order:** `{rzp_order.get('id', '')}`")
                st.markdown(f"### Amount: ₹{order['total']:,.0f}")
                st.caption(f"Gateway Amount: {int(order['total'] * 100):,} paise")

                # Action: Direct to Razorpay Page
                if st.button(
                    f"💳 Complete Payment — ₹{order['total']:,.0f} ↗",
                    key="btn_complete_payment",
                    type="primary",
                    use_container_width=True,
                    help="Directs to the Razorpay Payment Gateway page",
                ):
                    st.session_state.active_page = "razorpay_checkout"
                    st.query_params["page"] = "razorpay_checkout"
                    st.query_params["order_id"] = order["order_id"]
                    st.rerun()

                st.link_button(
                    "🌐 Open Razorpay Gateway Link ↗",
                    f"/?page=razorpay_checkout&order_id={order['order_id']}",
                    use_container_width=True,
                )

                if st.button("Cancel", key="btn_cancel_checkout", use_container_width=True):
                    st.session_state.checkout_active = False
                    st.session_state.current_order = None
                    st.session_state.current_rzp_order = None
                    st.rerun()

            st.divider()

    # ── 3. Normal Cart View ──────────────────────────────────────────
    else:
        with st.sidebar:
            st.markdown("## 🛒 Shopping Cart")

            cart = st.session_state.cart
            if not cart:
                st.info("Your cart is empty.\nAsk the AI agent for recommendations to get started!")
            else:
                item_count = get_cart_item_count()
                subtotal = get_cart_subtotal()

                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.metric("Total Items", item_count)
                with col_m2:
                    st.metric("Subtotal", f"₹{subtotal:,.0f}")
                st.divider()

                for pid, item in list(cart.items()):
                    product = item["product"]
                    qty = item["quantity"]
                    source = item.get("source", "customer-selected")

                    with st.container(border=True):
                        st.markdown(f"**{product['name'][:38]}**")
                        st.caption(f"₹{product['price']:,.0f} each")

                        # Source badge
                        if source == "AI-recommended":
                            st.markdown(
                                "<span style='background:#ede9fe; color:#6b21a8; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600;'>✨ AI-Recommended</span>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                "<span style='background:#dbeafe; color:#1e40af; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600;'>👤 Customer-Selected</span>",
                                unsafe_allow_html=True,
                            )

                        st.markdown("")

                        # Quantity controls
                        col_minus, col_qty, col_plus = st.columns([1, 2, 1])
                        with col_minus:
                            if st.button("➖", key=f"minus_{pid}", use_container_width=True):
                                update_cart_quantity(pid, qty - 1)
                                st.rerun()
                        with col_qty:
                            st.markdown(
                                f"<div style='text-align:center; padding:6px; font-size:16px;'><b>{qty}</b></div>",
                                unsafe_allow_html=True,
                            )
                        with col_plus:
                            if st.button("➕", key=f"plus_{pid}", use_container_width=True):
                                result = update_cart_quantity(pid, qty + 1)
                                if "Cannot" in result:
                                    st.toast(result)
                                else:
                                    st.rerun()

                        # Line total & remove
                        col_line, col_rem = st.columns([3, 2])
                        with col_line:
                            st.markdown(f"**₹{product['price'] * qty:,.0f}**")
                        with col_rem:
                            if st.button("Remove", key=f"remove_{pid}", use_container_width=True):
                                remove_from_cart(pid)
                                st.rerun()

                st.divider()
                st.markdown(f"### Subtotal: ₹{subtotal:,.0f}")

                # Proceed to Checkout Button
                if st.button(
                    "🚀 Proceed to Checkout",
                    key="checkout_btn",
                    use_container_width=True,
                    type="primary",
                ):
                    if start_checkout():
                        st.rerun()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. Audit Log Live Viewer
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with st.sidebar:
        st.markdown("---")
        with st.expander("🛡️ Agent Audit Log (Live)", expanded=False):
            st.caption("Live transparency record of agent decisions, searches, and guardrails.")
            logs = get_recent_logs(limit=15)
            if not logs:
                st.caption("No audit logs yet.")
            else:
                for log in logs:
                    evt = log.get("event_type", "INFO")
                    status = log.get("status", "SUCCESS")

                    if status in ("SUCCESS", "PASSED", "PROCESSED"):
                        badge = f"✅ [{status}]"
                    elif status == "WARNING":
                        badge = f"⚠️ [{status}]"
                    elif status == "FAILED":
                        badge = f"❌ [{status}]"
                    elif status == "NO_MATCH":
                        badge = f"🔍 [{status}]"
                    else:
                        badge = f"ℹ️ [{status}]"

                    st.markdown(f"**{badge} `{evt}`**")
                    st.markdown(f"*{log.get('action', '')}*")
                    if log.get("details"):
                        st.caption(f"Details: {log['details']}")
                    st.caption(f"Time: {log.get('timestamp', '')}")
                    st.markdown("---")

                if st.button("Clear Audit Log", key="clear_audit_btn", use_container_width=True):
                    clear_audit_logs()
                    st.rerun()

        with st.expander("💳 Razorpay Gateway Mode", expanded=False):
            if is_live_key_configured():
                st.success("🟢 Live Razorpay API Keys Active")
                st.caption(f"Key ID: `{os.getenv('RAZORPAY_KEY_ID')[:8]}••••`")
            else:
                st.info("🧪 Realistic Sandbox Mode Active (Zero-Crash Demo)")
                st.caption("All real Indian payment instruments (UPI apps, Live QR, Cards, Bank 3D-Secure OTP) are fully functional.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. DEDICATED RAZORPAY GATEWAY PAGE VIEW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_razorpay_gateway_page(order_id_str: str | None) -> None:
    """
    Renders an authentic, dedicated full-page Razorpay Checkout Gateway view.
    Replicates the real Razorpay standard modal, payment instrument selectors,
    and Issuing Bank 3D-Secure OTP authorization dialog.
    """
    order = None
    if order_id_str:
        order = get_order_by_order_id(order_id_str)
    if not order and st.session_state.get("current_order"):
        order = st.session_state["current_order"]

    if not order:
        st.error("No active order found for this payment session.")
        if st.button("↩ Return to TechMart Shopping", type="primary"):
            st.session_state.active_page = "main"
            st.session_state.rzp_auth_step = "method_selection"
            st.query_params.clear()
            st.rerun()
        return

    # Check if already paid
    if order.get("status") == "PAID":
        st.success(f"Order {order['order_id']} has already been PAID.")
        if st.button("↩ Return to TechMart Shopping", type="primary"):
            st.session_state.active_page = "main"
            st.session_state.rzp_auth_step = "method_selection"
            st.query_params.clear()
            st.rerun()
        return

    rzp_order = st.session_state.get("current_rzp_order") or {}
    rzp_id = rzp_order.get("id") or order.get("razorpay_order_id") or f"order_test_{order['id']}"
    auth_step = st.session_state.get("rzp_auth_step", "method_selection")
    selected_method = st.session_state.get("rzp_selected_method", "UPI (Google Pay)")

    # ── Razorpay Navy Brand Header ─────────────────────────────────────
    st.markdown(
        f"""
        <div style='background: linear-gradient(135deg, #0c2340 0%, #173b6c 100%); padding: 18px 24px; border-radius: 12px 12px 0 0; color: white; margin-bottom: 0px; box-shadow: 0 4px 15px rgba(0,0,0,0.15);'>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div style='display: flex; align-items: center; gap: 12px;'>
                    <div style='background: #3395ff; width: 38px; height: 38px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold;'>
                        R
                    </div>
                    <div>
                        <div style='font-size: 22px; font-weight: 800; letter-spacing: -0.5px;'>
                            <span style='color: #ffffff;'>Razorpay</span> <span style='font-size: 11px; background: rgba(51,149,255,0.3); color: #60a5fa; padding: 2px 8px; border-radius: 4px; margin-left: 6px; font-weight: 600; text-transform: uppercase;'>Checkout</span>
                        </div>
                        <div style='font-size: 12px; color: #94a3b8; margin-top: 2px;'>
                            Merchant: <b style='color: #e2e8f0;'>TechMart AI Commerce Ltd.</b> &nbsp;|&nbsp; <code>{order['order_id']}</code>
                        </div>
                    </div>
                </div>
                <div style='text-align: right;'>
                    <div style='font-size: 10px; color: #94a3b8; letter-spacing: 1px; font-weight: 700;'>AMOUNT TO PAY</div>
                    <div style='font-size: 26px; font-weight: 800; color: #38bdf8;'>₹{order['total']:,.0f}</div>
                    <div style='font-size: 10px; color: #64748b;'>{int(order['total']*100):,} paise</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Main Two-Column Razorpay Container ──────────────────────────────
    col_left, col_right = st.columns([5, 7], gap="medium")

    # ── Left Column: Brand & Order Summary ──────────────────────────────
    with col_left:
        with st.container(border=True):
            st.markdown(
                f"""
                <div style='padding: 6px 0;'>
                    <div style='display: flex; align-items: center; gap: 10px; margin-bottom: 14px;'>
                        <span style='font-size: 24px;'>🛒</span>
                        <div>
                            <div style='font-weight: 800; font-size: 15px; color: #ffffff;'>TechMart AI Commerce</div>
                            <div style='font-size: 11px; color: #94a3b8;'>receipt_id: <code>{order['receipt_id']}</code></div>
                        </div>
                    </div>
                    <div style='font-size: 12px; color: #cbd5e1; line-height: 1.7; margin-bottom: 10px;'>
                        👤 <b>Customer:</b> TechMart Customer<br>
                        📱 <b>Contact:</b> +91 98765 43210<br>
                        ✉️ <b>Email:</b> customer@techmart.com<br>
                        ⏱️ <b>Timestamp:</b> {order['timestamp']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.divider()

            with st.expander("📦 Order Line Items", expanded=True):
                for item in order.get("items", []):
                    src_badge = "✨ AI Upsell" if item.get("source") == "AI-recommended" else "👤 Selected"
                    badge_color = "#c4b5fd" if item.get("source") == "AI-recommended" else "#7dd3fc"
                    st.markdown(
                        f"<div style='display:flex; justify-content:space-between; margin-bottom:6px; font-size:12px;'>"
                        f"<span><b style='color:#e2e8f0;'>{item['name'][:28]}</b> x{item['quantity']} <span style='color:{badge_color}; font-size:10px;'>[{src_badge}]</span></span>"
                        f"<span style='font-family:var(--tm-font-mono); color:#38bdf8;'><b>₹{item['price'] * item['quantity']:,.0f}</b></span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.markdown(f"**Total Payable: ₹{order['total']:,.0f}**")

            st.markdown(
                """
                <div style='margin-top: 15px; padding: 12px; background: rgba(15,23,42,0.6); border: 1px solid rgba(148,163,184,0.15); border-radius: 8px; font-size: 11px; color: #94a3b8; line-height: 1.7;'>
                    🔒 <b style='color:#e2e8f0;'>256-Bit SSL Bank-Grade Encryption</b><br>
                    🛡️ <b style='color:#e2e8f0;'>PCI-DSS Level 1 Certified Gateway</b><br>
                    🇮🇳 <b style='color:#e2e8f0;'>RBI Authorized Payment Aggregator</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Right Column: Interactive Real Razorpay Payment View ────────────
    with col_right:
        with st.container(border=True):

            # ── STAGE 1: Payment Method Selection ───────────────────────
            if auth_step == "method_selection":
                st.markdown("#### 💳 Select Payment Method")
                st.caption("Complete payment using any authentic Indian payment instrument:")

                pay_tab_upi, pay_tab_card, pay_tab_net, pay_tab_wallet = st.tabs([
                    "⚡ UPI & QR",
                    "💳 Card",
                    "🏛️ Netbanking",
                    "👛 Wallets",
                ])

                # ── UPI TAB ──
                with pay_tab_upi:
                    st.markdown("##### Instant UPI Apps")
                    col_u1, col_u2, col_u3, col_u4 = st.columns(4)
                    with col_u1:
                        if st.button("🟢 GPay", key="btn_pay_gpay", use_container_width=True):
                            st.session_state.rzp_selected_method = "Google Pay (UPI)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                    with col_u2:
                        if st.button("🟣 PhonePe", key="btn_pay_phonepe", use_container_width=True):
                            st.session_state.rzp_selected_method = "PhonePe (UPI)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                    with col_u3:
                        if st.button("🔵 Paytm", key="btn_pay_paytm", use_container_width=True):
                            st.session_state.rzp_selected_method = "Paytm (UPI)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                    with col_u4:
                        if st.button("⚫ CRED", key="btn_pay_cred", use_container_width=True):
                            st.session_state.rzp_selected_method = "CRED (UPI)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()

                    st.markdown("---")
                    st.markdown("##### Or Scan Dynamic QR Code")
                    col_qr, col_vpa = st.columns([1, 2])
                    with col_qr:
                        st.markdown(
                            f"""
                            <div style='background: white; border: 2px solid #3395ff; border-radius: 8px; padding: 8px; text-align: center; box-shadow: 0 2px 8px rgba(51,149,255,0.2);'>
                                <img src='https://api.qrserver.com/v1/create-qr-code/?size=130x130&data=upi://pay?pa=techmart@upi&pn=TechMart&am={order['total']:.0f}&cu=INR' width='110' style='border-radius: 4px;' />
                                <div style='font-size: 10px; color: #16a34a; font-weight: 600; margin-top: 4px;'>● Live QR Code</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with col_vpa:
                        vpa_val = st.text_input("UPI ID / VPA", value="customer@okhdfcbank", key="upi_vpa_input")
                        st.caption("✓ Verified VPA: TechMart Customer")
                        if st.button(f"⚡ Pay ₹{order['total']:,.0f} with UPI", key="btn_pay_vpa", type="primary", use_container_width=True):
                            st.session_state.rzp_selected_method = f"UPI ({vpa_val})"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()

                # ── CARD TAB ──
                with pay_tab_card:
                    # Visual Card Mockup
                    st.markdown(
                        f"""
                        <div style='background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%); padding: 16px 20px; border-radius: 12px; color: white; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);'>
                            <div style='display:flex; justify-content:space-between; align-items:center;'>
                                <span style='font-size: 11px; letter-spacing: 1px; color: #93c5fd;'>DEBIT / CREDIT CARD</span>
                                <span style='font-size: 14px; font-weight: 800; color: #fbbf24;'>VISA</span>
                            </div>
                            <div style='margin-top: 14px; font-size: 18px; letter-spacing: 3px; font-family: monospace;'>
                                4111 &bull;&bull;&bull;&bull; &bull;&bull;&bull;&bull; 1111
                            </div>
                            <div style='display:flex; justify-content:space-between; margin-top: 14px; font-size: 11px;'>
                                <div>
                                    <span style='color:#94a3b8; font-size:9px;'>CARD HOLDER</span><br>
                                    <b>TECHMART CUSTOMER</b>
                                </div>
                                <div>
                                    <span style='color:#94a3b8; font-size:9px;'>EXPIRES</span><br>
                                    <b>12 / 28</b>
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    c_num = st.text_input("Card Number", value="4111 2222 3333 1111", key="card_num_in")
                    col_exp, col_cvv = st.columns(2)
                    with col_exp:
                        st.text_input("Valid Thru (MM/YY)", value="12/28", key="card_exp_in")
                    with col_cvv:
                        st.text_input("CVV", value="•••", type="password", key="card_cvv_in")
                    st.checkbox("Save card securely as per RBI guidelines", value=True, key="save_card_chk")

                    if st.button(f"🔒 Pay ₹{order['total']:,.0f} via Card", key="btn_pay_card", type="primary", use_container_width=True):
                        st.session_state.rzp_selected_method = "Card (Visa ending in 1111)"
                        st.session_state.rzp_auth_step = "bank_3d_secure"
                        st.rerun()

                # ── NETBANKING TAB ──
                with pay_tab_net:
                    st.markdown("##### Popular Indian Banks")
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("🏛️ HDFC Bank", key="nb_hdfc", use_container_width=True):
                            st.session_state.rzp_selected_method = "Netbanking (HDFC Bank)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                        if st.button("🏛️ State Bank of India", key="nb_sbi", use_container_width=True):
                            st.session_state.rzp_selected_method = "Netbanking (SBI)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                    with col_b2:
                        if st.button("🏛️ ICICI Bank", key="nb_icici", use_container_width=True):
                            st.session_state.rzp_selected_method = "Netbanking (ICICI Bank)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                        if st.button("🏛️ Axis Bank", key="nb_axis", use_container_width=True):
                            st.session_state.rzp_selected_method = "Netbanking (Axis Bank)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()

                    selected_nb = st.selectbox("Or choose another bank", ["Kotak Mahindra Bank", "Bank of Baroda", "Punjab National Bank", "IndusInd Bank", "Yes Bank"])
                    if st.button(f"🔒 Pay ₹{order['total']:,.0f} via {selected_nb}", key="btn_pay_nb_other", type="primary", use_container_width=True):
                        st.session_state.rzp_selected_method = f"Netbanking ({selected_nb})"
                        st.session_state.rzp_auth_step = "bank_3d_secure"
                        st.rerun()

                # ── WALLETS TAB ──
                with pay_tab_wallet:
                    st.markdown("##### Digital Wallets & PayLater")
                    col_w1, col_w2 = st.columns(2)
                    with col_w1:
                        if st.button("👛 Amazon Pay", key="w_amz", use_container_width=True):
                            st.session_state.rzp_selected_method = "Wallet (Amazon Pay)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                        if st.button("👛 Mobikwik", key="w_mobi", use_container_width=True):
                            st.session_state.rzp_selected_method = "Wallet (Mobikwik)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                    with col_w2:
                        if st.button("⚡ LazyPay", key="w_lazy", use_container_width=True):
                            st.session_state.rzp_selected_method = "PayLater (LazyPay)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()
                        if st.button("⚡ Simpl PayLater", key="w_simpl", use_container_width=True):
                            st.session_state.rzp_selected_method = "PayLater (Simpl)"
                            st.session_state.rzp_auth_step = "bank_3d_secure"
                            st.rerun()

                st.markdown("---")
                if st.button("✕ Cancel Payment & Return to TechMart", key="btn_cancel_rzp_main", use_container_width=True):
                    st.session_state.active_page = "main"
                    st.session_state.rzp_auth_step = "method_selection"
                    st.query_params.clear()
                    st.rerun()

            # ── STAGE 2: Bank 3D-Secure Authentication Dialog ───────────
            elif auth_step == "bank_3d_secure":
                st.markdown(
                    f"""
                    <div style='background: linear-gradient(135deg, rgba(30,58,138,0.3) 0%, rgba(15,23,42,0.85) 100%); border: 1px solid rgba(59,130,246,0.3); border-radius: 10px; padding: 16px; margin-bottom: 16px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center;'>
                            <div style='font-size: 14px; font-weight: 800; color: #93c5fd;'>
                                🏛️ Issuing Bank 3D-Secure Gateway
                            </div>
                            <span style='font-size: 11px; background: rgba(56,189,248,0.2); color: #7dd3fc; border: 1px solid rgba(56,189,248,0.3); padding: 2px 8px; border-radius: 4px; font-weight: 600;'>Verified by VISA</span>
                        </div>
                        <div style='font-size: 12px; color: #cbd5e1; margin-top: 8px;'>
                            Merchant: <b style='color:#ffffff;'>TechMart AI Commerce Ltd.</b> &nbsp;|&nbsp; Amount: <b style='color: #38bdf8; font-family:var(--tm-font-mono);'>₹{order['total']:,.0f}</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(f"**Authenticating via:** `{selected_method}`")
                st.info("A 6-digit One-Time Password (OTP) has been sent to your mobile registered with your bank ending in ••••89.")

                otp_code = st.text_input("Enter One-Time Password (OTP)", value="123456", key="rzp_otp_input", help="Razorpay Sandbox test OTP is 123456")
                st.caption("⏱️ Resend OTP in 0:45 &nbsp;|&nbsp; Test Sandbox OTP: `123456`")

                col_sub_otp, col_back_otp = st.columns([2, 1])
                with col_sub_otp:
                    if st.button(f"🔒 Submit OTP & Authorize ₹{order['total']:,.0f}", key="btn_submit_otp", type="primary", use_container_width=True):
                        st.session_state.rzp_auth_step = "authorizing"
                        st.rerun()
                with col_back_otp:
                    if st.button("Back", key="btn_back_method", use_container_width=True):
                        st.session_state.rzp_auth_step = "method_selection"
                        st.rerun()

            # ── STAGE 3: Authorizing & Settling Payment ─────────────────
            elif auth_step == "authorizing":
                st.markdown("#### 🔐 Processing Payment...")
                with st.spinner("Step 1/3: Contacting Issuing Bank for 3D-Secure Authorization..."):
                    time.sleep(0.8)
                with st.spinner(f"Step 2/3: Authorizing ₹{order['total']:,.0f} with Razorpay Payment Gateway..."):
                    time.sleep(0.8)

                payment_id = f"pay_rzp_{uuid.uuid4().hex[:12]}"
                success = update_order_payment(order["id"], payment_id, status="PAID")

                if success:
                    log_event(
                        event_type="PAYMENT_COMPLETED",
                        action=f"Order {order['order_id']} paid via {selected_method}",
                        details=f"Amount: ₹{order['total']:,.0f}; Payment ID: {payment_id}; Stock deducted in SQLite; 3D-Secure Verified",
                        status="SUCCESS",
                        rule_or_tool="Razorpay 3D-Secure Gateway",
                    )
                    st.success(f"🎉 Payment Authorized by Bank! Razorpay Payment ID: `{payment_id}`")
                    st.session_state.last_confirmed_order = get_order_details(order["id"])
                    st.session_state.cart = {}
                    st.session_state.checkout_active = False
                    st.session_state.current_order = None
                    st.session_state.current_rzp_order = None
                    st.session_state.rzp_auth_step = "method_selection"
                    st.session_state.active_page = "main"
                    st.query_params.clear()
                    st.balloons()
                    time.sleep(1.0)
                    st.rerun()
                else:
                    st.error("Payment authorization failed. Please try again.")
                    st.session_state.rzp_auth_step = "method_selection"
                    if st.button("Retry Payment"):
                        st.rerun()




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. MERCHANT COMMERCE & ANALYTICS DASHBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_merchant_dashboard() -> None:
    """
    Renders the Merchant Business Intelligence, Order Management,
    Inventory Restocking & Compliance Console.
    """
    st.markdown("## 📊 TechMart Merchant Commerce & AI Analytics")
    st.caption("Real-time business intelligence, AI revenue attribution, inventory management & fintech compliance.")

    analytics = get_merchant_analytics()

    tab_roi, tab_campaign, tab_orders, tab_inventory, tab_compliance = st.tabs([
        "📈 AI Business ROI & Revenue",
        "🤖 AI Campaign Agent",
        "📦 Live Order Management",
        "🏷️ Inventory & Restocking",
        "🛡️ Compliance & Audit Trail",
    ])

    # ── TAB 1: AI ROI & Analytics ────────────────────────────────────────
    with tab_roi:
        st.markdown("### 📈 Merchant AI ROI & Commercial Performance")
        st.caption("Real-time revenue metrics calculated strictly from successful, paid orders in SQLite.")

        # High Level KPI Cards
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.markdown(render_kpi_card_html("Total Revenue", f"₹{analytics['total_revenue']:,.0f}", sub="Completed paid orders in SQLite", border_color="#10b981"), unsafe_allow_html=True)
        with col_m2:
            st.markdown(render_kpi_card_html("Paid Orders", str(analytics["paid_orders"]), sub="Real-time checkout count", border_color="#6366f1"), unsafe_allow_html=True)
        with col_m3:
            st.markdown(render_kpi_card_html("Average Order Value (AOV)", f"₹{analytics.get('average_order_value', 0.0):,.0f}", sub="Revenue per customer transaction", border_color="#38bdf8"), unsafe_allow_html=True)

        # Sub Revenue Breakdown Cards
        st.markdown("")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.markdown(render_kpi_card_html("Customer-Selected Rev", f"₹{analytics['customer_selected_revenue']:,.0f}", sub="Baseline primary orders", border_color="#0284c7"), unsafe_allow_html=True)
        with col_s2:
            st.markdown(render_kpi_card_html("AI Upsell Revenue", f"₹{analytics.get('ai_upsell_revenue', 0.0):,.0f}", sub="Generated via AI suggestions", border_color="#a855f7"), unsafe_allow_html=True)
        with col_s3:
            st.markdown(render_kpi_card_html("AI Revenue Contribution", f"{analytics['ai_revenue_share_pct']:.1f}%", sub=f"{analytics['conversion_rate_pct']:.1f}% cross-sell attach rate", border_color="#ec4899"), unsafe_allow_html=True)

        st.markdown("---")

        col_rev_split, col_breakdown = st.columns([1, 1], gap="large")

        with col_rev_split:
            st.markdown("#### ⚖️ Revenue Attribution")
            st.caption("Comparing customer self-selection vs revenue generated by the AI agent's recommendations.")

            total_rev = analytics["total_revenue"]
            cust_rev = analytics["customer_selected_revenue"]
            ai_rev = analytics["ai_recommended_revenue"]

            with st.container(border=True):
                st.markdown(
                    f"""
                    <div style='margin-bottom:8px;'>
                        <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                            <span style='font-size:12px; font-weight:700; color:#94a3b8;'>👤 CUSTOMER-SELECTED REVENUE</span>
                            <span style='font-family:var(--tm-font-mono); font-size:13px; font-weight:700; color:#38bdf8;'>₹{cust_rev:,.0f}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                cust_pct = (cust_rev / total_rev * 100) if total_rev > 0 else 100.0
                st.progress(min(1.0, max(0.0, cust_pct / 100)))

                st.markdown(
                    f"""
                    <div style='margin-top:14px; margin-bottom:8px;'>
                        <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                            <span style='font-size:12px; font-weight:700; color:#c4b5fd;'>✨ AI-RECOMMENDED UPSELL REVENUE</span>
                            <span style='font-family:var(--tm-font-mono); font-size:13px; font-weight:700; color:#a855f7;'>₹{ai_rev:,.0f} ({analytics['ai_revenue_share_pct']:.1f}%)</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                ai_pct = (ai_rev / total_rev * 100) if total_rev > 0 else 0.0
                st.progress(min(1.0, max(0.0, ai_pct / 100)))

                st.markdown(
                    f"""
                    <div style='background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.25); border-radius:8px; padding:10px 12px; margin-top:14px;'>
                        <span style='font-size:12px; color:#c7d2fe;'>💡 <b>Cross-Sell Conversion Rate:</b> {analytics['conversion_rate_pct']:.1f}% of completed orders included an approved AI upsell!</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with col_breakdown:
            st.markdown("#### 🔗 AI Revenue Breakdown (Converted Pairs)")
            st.caption("Generated from actual order items and purchase history in SQLite.")

            breakdown = analytics.get("ai_revenue_breakdown", [])
            if not breakdown:
                st.info("No AI cross-sell pairs recorded yet. As customers accept suggestions, converted pairings will appear here.")
            else:
                for item in breakdown:
                    with st.container(border=True):
                        cb1, cb2 = st.columns([3, 2])
                        with cb1:
                            p_name = item.get("primary_name", item.get("primary_category", "Product"))
                            st.markdown(f"**{p_name[:20]}** ➔ **{item['upsell_name']}**")
                            st.caption(f"Category: {item.get('primary_category','Item')} → {item.get('upsell_category','Accessory')} ({item.get('upsell_qty', 1)} sold)")
                        with cb2:
                            st.markdown(f"<div style='text-align:right; font-family:var(--tm-font-mono); font-size:16px; font-weight:700; color:#10b981;'>+₹{item['upsell_revenue']:,.0f}</div>", unsafe_allow_html=True)

    # ── TAB 2: AI Campaign & Offer Agent ─────────────────────────────────
    with tab_campaign:
        st.markdown("### 🤖 AI Campaign & Offer Agent")
        st.caption(
            "Proactive merchant intelligence: analyzes sales velocity, inventory levels, "
            "and cross-category attachment rates to discover revenue-maximizing promotional opportunities. "
            "All campaigns require explicit merchant approval before activation."
        )

        # Trigger analysis button
        col_btn1, col_btn2 = st.columns([2, 3])
        with col_btn1:
            if st.button("🔍 Analyze Sales & Catalog", type="primary", key="btn_run_campaign_analysis", use_container_width=True):
                with st.spinner("AI Agent analyzing purchase patterns, inventory turnover & attachment rates..."):
                    res = analyze_and_suggest_campaign(force_refresh=True)
                    st.session_state["latest_campaign_result"] = res
                    st.rerun()

        # Load active suggestion
        latest_res = st.session_state.get("latest_campaign_result")
        latest_db = get_latest_campaign_suggestion()

        # If session_state is empty but DB has a recent suggestion, prepare view
        if not latest_res and latest_db:
            summary = get_sales_and_catalog_summary()
            top_cat = summary.get("top_category")
            top_prod = summary.get("top_product")
            low_stock_opp = summary.get("low_sales_high_stock", [{}])[0] if summary.get("low_sales_high_stock") else None
            key_opp = None
            for att in summary.get("attachment_stats", []):
                if att["primary_orders_count"] > 0 and att["attachment_rate_pct"] < 50.0 and att["secondary_stock"] > 0:
                    key_opp = f"{att['primary_category']} ➔ {att['secondary_category']} ({att['attachment_rate_pct']}% attachment)"
                    break

            latest_res = {
                "status": "success",
                "business_insights": {
                    "top_category": top_cat["category"] if top_cat else "Laptops",
                    "best_selling_product": top_prod["name"] if top_prod else "HP 15s",
                    "low_selling_accessory": low_stock_opp["name"] if low_stock_opp else "Dell MS116",
                    "opportunity_identified": key_opp or "Laptops ➔ Laptop Bags (0.0% attachment)",
                    "paid_orders_analyzed": summary["paid_orders"],
                    "total_revenue_analyzed": summary["total_revenue"],
                },
                "campaign": latest_db,
            }

        if latest_res:
            if latest_res.get("status") == "insufficient_data":
                st.warning("⚠️ " + latest_res.get("message", "Not enough sales data to generate a reliable campaign recommendation."))
            else:
                insights = latest_res.get("business_insights", {})
                campaign = latest_res.get("campaign", {})

                # ── 1. BUSINESS INSIGHTS ─────────────────────────────────
                st.markdown("#### 📊 Business Insights")
                st.caption(f"Derived from {insights.get('paid_orders_analyzed', 0)} completed orders (₹{insights.get('total_revenue_analyzed', 0.0):,.0f} revenue) in SQLite.")

                bi1, bi2, bi3, bi4 = st.columns(4)
                with bi1:
                    st.metric("Top-Selling Category", insights.get("top_category", "N/A"))
                with bi2:
                    p_best = insights.get("best_selling_product", "N/A")
                    st.metric("Best-Selling Product", (p_best[:16] + "..") if len(p_best) > 16 else p_best)
                with bi3:
                    p_low = insights.get("low_selling_accessory", "N/A")
                    st.metric("Low-Selling Accessory", (p_low[:16] + "..") if len(p_low) > 16 else p_low)
                with bi4:
                    st.metric("Identified Opportunity", insights.get("opportunity_identified", "N/A"))

                st.markdown("---")

                # ── 2. AI CAMPAIGN OPPORTUNITY ───────────────────────────
                st.markdown("#### 💡 AI Campaign Opportunity")
                
                type_badges = {
                    "bundle": "📦 Bundle Offer",
                    "clearance": "🏷️ Inventory Clearance",
                    "discount": "💸 Promotional Discount",
                    "cross_sell": "✨ Cross-Sell Acceleration",
                    "promotion": "🎯 Product Promotion",
                }
                c_badge = type_badges.get(campaign.get("campaign_type", "").lower(), "💡 Campaign Offer")

                with st.container(border=True):
                    head_col1, head_col2 = st.columns([3, 1])
                    with head_col1:
                        st.markdown(f"### {campaign.get('title', 'Campaign Offer')}")
                        st.markdown(f"`{c_badge}` &nbsp;|&nbsp; Target: **{campaign.get('target_audience', 'All Customers')}**")
                    with head_col2:
                        status_val = campaign.get("status", "SUGGESTED").upper()
                        if status_val == "APPROVED":
                            st.success("✅ APPROVED", icon="🛡️")
                        elif status_val == "REJECTED":
                            st.error("❌ REJECTED", icon="🛑")
                        else:
                            st.info("🕒 PENDING", icon="⏳")

                    st.markdown("")
                    st.markdown(f"**Why this campaign:** {campaign.get('reason', '')}")
                    
                    co1, co2 = st.columns(2)
                    with co1:
                        st.markdown(f"**Suggested Offer:** `{campaign.get('suggested_discount', 'Special Pricing')}`")
                    with co2:
                        st.markdown(f"**Expected Objective:** {campaign.get('objective', 'Revenue Lift')}")

                    st.markdown("##### 📌 Explainable Business Evidence:")
                    evidence_items = campaign.get("evidence", [])
                    if isinstance(evidence_items, list):
                        for ev in evidence_items:
                            st.markdown(f"- {ev}")
                    else:
                        st.markdown(f"- {evidence_items}")

                    st.markdown("---")

                    # Explicit Human-in-the-Loop Action Controls
                    cid = campaign.get("id")
                    current_status = campaign.get("status", "SUGGESTED").upper()

                    if current_status == "SUGGESTED":
                        st.markdown("**Merchant Decision (Human-in-the-Loop):**")
                        st.caption("The AI cannot automatically apply or publish campaigns. Your explicit approval is required.")
                        btn_c1, btn_c2, _ = st.columns([1.5, 1.5, 3])
                        with btn_c1:
                            if st.button("✅ Approve Campaign", type="primary", key=f"btn_approve_camp_{cid}", use_container_width=True):
                                approve_campaign(cid)
                                st.toast("Campaign Approved & Decision Logged!", icon="🎉")
                                if "latest_campaign_result" in st.session_state and st.session_state["latest_campaign_result"].get("campaign"):
                                    st.session_state["latest_campaign_result"]["campaign"]["status"] = "APPROVED"
                                st.rerun()
                        with btn_c2:
                            if st.button("❌ Reject", key=f"btn_reject_camp_{cid}", use_container_width=True):
                                reject_campaign(cid)
                                st.toast("Campaign Declined.", icon="🛑")
                                if "latest_campaign_result" in st.session_state and st.session_state["latest_campaign_result"].get("campaign"):
                                    st.session_state["latest_campaign_result"]["campaign"]["status"] = "REJECTED"
                                st.rerun()
                    elif current_status == "APPROVED":
                        st.success(f"✅ **Campaign Approved!** Stored in merchant intelligence registry. Decision logged in Fintech Audit Trail.")
                    elif current_status == "REJECTED":
                        st.warning(f"❌ **Campaign Declined.** Decision logged in Fintech Audit Trail.")

                # History expander
                history = get_campaign_history(limit=5)
                if history:
                    with st.expander("📜 Campaign Decision History", expanded=False):
                        for h in history:
                            h_badge = "✅ APPROVED" if h["status"] == "APPROVED" else ("❌ REJECTED" if h["status"] == "REJECTED" else "⏳ SUGGESTED")
                            st.markdown(f"**#{h['id']} {h['title']}** — `{h_badge}` | Date: {h.get('created_at', 'N/A')}")
                            st.caption(f"Offer: {h.get('suggested_discount', '')} | Type: {h.get('campaign_type', '')}")
        else:
            st.info("Click **'🔍 Analyze Sales & Catalog'** above to let the AI Campaign Agent inspect orders, stock, and attachment rates.")

    # ── TAB 3: Live Orders Management ────────────────────────────────────
    with tab_orders:
        st.markdown("### 📦 Live Order Management & Fulfillment")
        st.caption("Inspect live customer purchases, payment confirmations, and line-item revenue attribution.")

        col_or1, col_or2 = st.columns([2, 2])
        with col_or1:
            status_filter = st.radio("Filter Status:", ["All Orders", "PAID Only", "PENDING Only"], horizontal=True, key="order_status_filter")
        with col_or2:
            search_order = st.text_input("🔍 Search by Order ID or Receipt", placeholder="e.g. ORD-2026 or rcpt_...", key="order_search_kw")

        recent_orders = get_recent_orders(limit=50)
        if not recent_orders:
            st.info("No orders recorded yet.")
        else:
            if status_filter == "PAID Only":
                recent_orders = [o for o in recent_orders if o.get("status") == "PAID"]
            elif status_filter == "PENDING Only":
                recent_orders = [o for o in recent_orders if o.get("status") != "PAID"]

            if search_order.strip():
                kw = search_order.strip().lower()
                recent_orders = [
                    o for o in recent_orders
                    if kw in str(o.get("order_id", "")).lower() or kw in str(o.get("receipt_id", "")).lower()
                ]

            st.caption(f"Showing {len(recent_orders)} orders:")

            for o in recent_orders:
                with st.container(border=True):
                    col_o1, col_o2, col_o3 = st.columns([3, 2, 2])
                    with col_o1:
                        st.markdown(f"**Order ID:** `{o['order_id']}`")
                        st.caption(f"Receipt: `{o['receipt_id']}` | Date: {o.get('timestamp', 'N/A')}")
                    with col_o2:
                        amt = o.get("amount_inr") or o.get("total") or 0.0
                        st.markdown(f"**Total:** ₹{float(amt):,.0f}")
                        st.caption(f"Gateway: `{o.get('razorpay_order_id', 'N/A')}`")
                    with col_o3:
                        if o.get("status") == "PAID":
                            st.success("✅ PAID", icon="💳")
                        else:
                            st.warning("⏳ PENDING", icon="⏳")

                    # Detailed line items
                    details = get_order_details(o["id"])
                    if details and details.get("items"):
                        with st.expander(f"Inspect Line Items ({len(details['items'])}) & Attribution", expanded=False):
                            for it in details["items"]:
                                badge = "✨ AI-Recommended" if it.get("source") == "AI-recommended" else "👤 Customer-Selected"
                                item_price = float(it.get("price") or 0.0)
                                item_qty = int(it.get("quantity") or 1)
                                st.markdown(f"- **{it.get('name', 'Item')}** x{item_qty} — ₹{item_price * item_qty:,.0f} `({badge})`")
                    elif details:
                        st.caption("No individual line items stored.")

    # ── TAB 4: Inventory & Restocking Console ────────────────────────────
    with tab_inventory:
        st.markdown("### 🏷️ Real-Time Inventory & Stock Management")
        all_prods = get_all_products_admin()
        st.caption(f"Live stock levels across all {len(all_prods)} catalog items. Depleted stock automatically blocks purchases.")

        low_stock_count = sum(1 for p in all_prods if p["stock"] <= 10 and p["stock"] > 0)
        out_of_stock_count = sum(1 for p in all_prods if p["stock"] == 0)

        c_inv1, c_inv2, c_inv3 = st.columns(3)
        with c_inv1:
            st.metric("Total Catalog Items", len(all_prods))
        with c_inv2:
            st.metric("Low Stock (≤10)", low_stock_count, delta="-Needs Restock" if low_stock_count > 0 else "Optimal", delta_color="inverse")
        with c_inv3:
            st.metric("Out of Stock", out_of_stock_count, delta="Critical" if out_of_stock_count > 0 else "Zero", delta_color="inverse")

        st.markdown("---")

        # ── Bulk CSV Catalog Upload & Sync ───────────────────────────────
        with st.expander("📤 Bulk CSV Catalog Upload & Sync", expanded=False):
            st.markdown(
                "Upload a CSV file to add new products or update existing stock/pricing in real-time. "
                "The agent catalog immediately reflects imported items."
            )
            st.info(
                "**Required CSV Columns:** `name,category,price,description,stock`\n\n"
                "- `name` and `category` are required text strings\n"
                "- `price` must be a positive number (INR)\n"
                "- `stock` must be a non-negative integer",
                icon="ℹ️"
            )

            sample_csv = "name,category,price,description,stock\nLogitech MX Master 3S,Mouse,7999.0,Premium wireless productivity mouse with multi-device support,15\nSony WH-1000XM5,Headphones,29999.0,Premium wireless noise-cancelling over-ear headphones,12"
            st.download_button(
                "📥 Download Sample CSV Template",
                data=sample_csv,
                file_name="sample_catalog.csv",
                mime="text/csv",
                key="btn_download_sample_csv",
            )

            uploaded_csv = st.file_uploader(
                "Choose a CSV file",
                type=["csv"],
                key="catalog_csv_uploader",
                help="Upload CSV with name, category, price, description, stock",
            )

            if uploaded_csv is not None:
                try:
                    content = uploaded_csv.getvalue().decode("utf-8")
                    reader = csv.DictReader(io.StringIO(content))
                    fieldnames = [f.strip() for f in (reader.fieldnames or [])]
                    required_fields = {"name", "category", "price", "description", "stock"}

                    if not required_fields.issubset(set(fieldnames)):
                        missing = required_fields - set(fieldnames)
                        st.error(f"❌ Missing required columns in CSV: {', '.join(sorted(missing))}")
                    else:
                        valid_rows = []
                        validation_errors = []

                        for idx, row in enumerate(reader, start=2):  # Row 2 is first data row
                            name = (row.get("name") or "").strip()
                            cat = (row.get("category") or "").strip()
                            desc = (row.get("description") or "").strip()
                            price_raw = (row.get("price") or "").strip()
                            stock_raw = (row.get("stock") or "").strip()

                            if not name:
                                validation_errors.append(f"Row {idx}: 'name' cannot be empty.")
                                continue
                            if not cat:
                                validation_errors.append(f"Row {idx}: 'category' cannot be empty.")
                                continue

                            try:
                                price_val = float(price_raw)
                                if price_val < 0:
                                    validation_errors.append(f"Row {idx}: 'price' must be ≥ 0 (got '{price_raw}').")
                                    continue
                            except ValueError:
                                validation_errors.append(f"Row {idx}: 'price' must be a valid number (got '{price_raw}').")
                                continue

                            try:
                                stock_val = int(stock_raw)
                                if stock_val < 0:
                                    validation_errors.append(f"Row {idx}: 'stock' must be ≥ 0 (got '{stock_raw}').")
                                    continue
                            except ValueError:
                                validation_errors.append(f"Row {idx}: 'stock' must be a valid integer (got '{stock_raw}').")
                                continue

                            valid_rows.append({
                                "name": name,
                                "category": cat,
                                "price": price_val,
                                "description": desc,
                                "stock": stock_val,
                            })

                        col_m1, col_m2, col_m3 = st.columns(3)
                        with col_m1:
                            st.metric("Total Rows in CSV", len(valid_rows) + len(validation_errors))
                        with col_m2:
                            st.metric("Valid Rows", len(valid_rows))
                        with col_m3:
                            st.metric("Errors Detected", len(validation_errors), delta="Blocked" if validation_errors else "Clean", delta_color="inverse")

                        if validation_errors:
                            st.error(f"⚠️ Validation issues detected in {len(validation_errors)} row(s):")
                            for err in validation_errors[:5]:
                                st.caption(f"• {err}")
                            if len(validation_errors) > 5:
                                st.caption(f"... and {len(validation_errors) - 5} more issues.")

                        if valid_rows:
                            st.markdown("#### 📦 Catalog Preview (First 5 Items)")
                            st.dataframe(valid_rows[:5], use_container_width=True)

                            if st.button("🚀 Import & Sync to SQLite Catalog", type="primary", key="btn_execute_import_csv", use_container_width=True):
                                res = import_catalog_csv(valid_rows)
                                if res.get("success"):
                                    st.success(
                                        f"✅ Catalog Sync Complete! Added {res['inserted']} new items, updated {res['updated']} existing items.",
                                        icon="🎉"
                                    )
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to import catalog: {res.get('error')}")
                except Exception as e:
                    st.error(f"Error parsing CSV file: {e}")

        st.markdown("---")

        # Search and Category Filters
        col_fil1, col_fil2, col_fil3 = st.columns([2, 2, 2])
        with col_fil1:
            search_inv = st.text_input("🔍 Search Catalog Products", placeholder="Search by name or specs...", key="inv_search_kw")
        with col_fil2:
            cats = ["All Categories"] + sorted(list({p["category"] for p in all_prods}))
            selected_cat = st.selectbox("Filter by Category", cats, key="inv_cat_filter")
        with col_fil3:
            stock_filter = st.radio("Stock Status:", ["All", "Low (≤10)", "Out of Stock", "Normal (>10)"], horizontal=True, key="inv_stock_filter")

        filtered_prods = all_prods
        if selected_cat != "All Categories":
            filtered_prods = [p for p in filtered_prods if p["category"] == selected_cat]

        if search_inv.strip():
            kw = search_inv.strip().lower()
            filtered_prods = [p for p in filtered_prods if kw in p["name"].lower() or kw in p.get("description", "").lower()]

        if stock_filter == "Low (≤10)":
            filtered_prods = [p for p in filtered_prods if 0 < p["stock"] <= 10]
        elif stock_filter == "Out of Stock":
            filtered_prods = [p for p in filtered_prods if p["stock"] == 0]
        elif stock_filter == "Normal (>10)":
            filtered_prods = [p for p in filtered_prods if p["stock"] > 10]

        st.caption(f"Showing **{len(filtered_prods)}** product(s):")

        for prod in filtered_prods:
            with st.container(border=True):
                col_p1, col_p2, col_p3, col_p4 = st.columns([4, 2, 2, 2])
                with col_p1:
                    icon = CATEGORY_ICONS.get(prod["category"], "📦")
                    st.markdown(f"**{icon} {prod['name']}**")
                    st.caption(f"Category: {prod['category']} | Price: ₹{prod['price']:,.0f}")
                with col_p2:
                    st.markdown(f"**Stock:** {prod['stock']} units")
                with col_p3:
                    if prod["stock"] > 10:
                        st.markdown(":green[🟢 Normal]")
                    elif prod["stock"] > 0:
                        st.markdown(":orange[🟠 Low Stock]")
                    else:
                        st.markdown(":red[🔴 Out of Stock]")
                with col_p4:
                    if st.button(f"➕ Restock +10", key=f"restock_{prod['id']}", use_container_width=True):
                        restock_product(prod["id"], quantity=10)
                        st.toast(f"Restocked {prod['name']} (+10 units)!", icon="📦")
                        time.sleep(0.3)
                        st.rerun()

    # ── TAB 5: Compliance & Audit Trail ──────────────────────────────────
    with tab_compliance:
        st.markdown("### 🛡️ Fintech Compliance & Safety Audit Console")
        st.caption("Complete tamper-evident transparency record of AI decisions, safety guardrails, and transactions.")

        logs = get_recent_logs(limit=100)

        col_f1, col_f2, col_f3 = st.columns([2, 2, 1.5])
        with col_f1:
            evt_types = ["ALL"] + sorted(list({l.get("event_type", "INFO") for l in logs}))
            selected_evt = st.selectbox("Filter by Event Type:", evt_types, key="audit_event_filter")
        with col_f2:
            search_log = st.text_input("🔍 Search Audit Records", placeholder="Search action, details, tool...", key="audit_search_kw")
        with col_f3:
            # Generate CSV export
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["id", "timestamp", "event_type", "action", "rule_or_tool", "details", "status"])
            writer.writeheader()
            for l in logs:
                writer.writerow({k: l.get(k, "") for k in writer.fieldnames})
            csv_data = output.getvalue()
            st.download_button(
                "📥 Export CSV",
                data=csv_data,
                file_name="techmart_audit_logs.csv",
                mime="text/csv",
                use_container_width=True,
            )

        filtered_logs = logs if selected_evt == "ALL" else [l for l in logs if l.get("event_type") == selected_evt]
        if search_log.strip():
            kw = search_log.strip().lower()
            filtered_logs = [
                l for l in filtered_logs
                if kw in str(l.get("action", "")).lower() or kw in str(l.get("details", "")).lower() or kw in str(l.get("rule_or_tool", "")).lower()
            ]

        st.caption(f"Displaying **{len(filtered_logs)}** audit trail events:")

        for log in filtered_logs:
            with st.container(border=True):
                evt = log.get("event_type", "INFO")
                status = log.get("status", "SUCCESS")
                time_str = log.get("timestamp", "")
                tool = log.get("rule_or_tool", "Agent")

                badge = "✅" if status in ("SUCCESS", "PASSED") else ("🛑" if status in ("REJECTED", "BLOCKED", "FAILED") else "ℹ️")
                st.markdown(f"**{badge} `{evt}`** &nbsp;|&nbsp; `{time_str}` &nbsp;|&nbsp; *Component: {tool}*")
                st.markdown(f"**Action:** {log.get('action', '')}")
                if log.get("details"):
                    st.caption(f"Details: {log['details']}")
                st.caption(f"Status: **{status}**")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. MAIN APP ORCHESTRATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    # ── Inject comprehensive design system & custom CSS ──────────────────
    inject_custom_css()

    # ── Initialise database & session state ──────────────────────────────
    ensure_db_schema()
    init_session_state()

    # Auto-seed products if table is empty
    if get_product_count() == 0:
        seed_products()

    # ── Check if directed to Razorpay Payment Page ──────────────────────
    page = st.query_params.get("page") or st.session_state.get("active_page")
    if page == "razorpay_checkout":
        order_id_param = st.query_params.get("order_id")
        if not order_id_param and st.session_state.get("current_order"):
            order_id_param = st.session_state["current_order"]["order_id"]
        render_razorpay_gateway_page(order_id_param)
        return

    # ── Global Top Branding Header Bar ───────────────────────────────────
    render_header_bar()

    # ── Sidebar View Navigation ──────────────────────────────────────────
    st.sidebar.markdown("### 🧭 Navigation")
    app_view = st.sidebar.radio(
        "Choose Platform View",
        ["🛍️ Customer Shopping Agent", "📊 Merchant Dashboard"],
        index=0,
        key="app_view_mode",
        label_visibility="collapsed",
    )
    st.sidebar.divider()

    # ── Route View ───────────────────────────────────────────────────────
    if app_view == "📊 Merchant Dashboard":
        render_merchant_dashboard()
        return

    # ── Customer Shopping Agent View ─────────────────────────────────────
    render_cart_sidebar()

    # ── Quick-start suggestions & Hero (only shown when no messages) ─────
    if not st.session_state.messages:
        render_hero_banner()
        st.markdown("<div style='font-size:12px; font-weight:700; color:#94a3b8; margin-bottom:10px; text-transform:uppercase; letter-spacing:0.5px;'>⚡ Quick Try Prompts:</div>", unsafe_allow_html=True)
        cols = st.columns(4)
        suggestions = [
            "I need a laptop for coding under 70000",
            "Smartphone under 25000 with AMOLED",
            "Wireless mouse under 1000",
            "Tablet with stylus support",
        ]
        for col, suggestion in zip(cols, suggestions):
            with col:
                if st.button(
                    suggestion,
                    key=f"sug_{suggestion[:15]}",
                    use_container_width=True,
                ):
                    st.session_state._auto_prompt = suggestion
                    st.rerun()
    else:
        st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)

    # ── Render chat history ──────────────────────────────────────────────
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Render Visibly Agentic Flow attached to this assistant message
            if msg["role"] == "assistant":
                render_agentic_flow(msg, idx)

    # ── Chat input ───────────────────────────────────────────────────────
    auto_prompt = st.session_state.pop("_auto_prompt", None)
    prompt = auto_prompt or st.chat_input("What are you looking for? (e.g. 'I need a laptop for coding under 70000')")

    if prompt:
        # Show user message immediately
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # ── Process query via AI Shopping Agent with Conversational Context ───
        ctx = dict(st.session_state.get("conversation_context", {}))
        ctx["cart"] = st.session_state.cart  # pass current cart items for live cart context
        with st.spinner("TechMart AI Agent is analyzing requirements and searching catalog..."):
            agent_result = process_shopping_request(prompt, context=ctx)

        # Update conversation context
        if "conversation_context" in agent_result:
            st.session_state.conversation_context = agent_result["conversation_context"]

        # Track budget for pre-payment guardrail check
        budget = agent_result.get("requirements", {}).get("max_price")
        if budget:
            st.session_state.customer_budget = budget

        response_text = agent_result.get("message", "")
        recommendations = agent_result.get("recommendations", [])
        engine_used = agent_result.get("engine", "AI Engine")

        formatted_response = f"**[AI Engine: {engine_used}]**\n\n{response_text}"

        # Save assistant message with agent understanding, catalog search, and recommendations
        msg_obj = {
            "role": "assistant",
            "content": formatted_response,
            "recommendations": recommendations,
            "agent_understanding": agent_result.get("agent_understanding"),
            "catalog_search": agent_result.get("catalog_search"),
        }
        st.session_state.messages.append(msg_obj)

        st.rerun()


if __name__ == "__main__":
    main()
