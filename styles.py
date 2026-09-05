"""
styles.py -- Comprehensive Design System & Custom UI Components for TechMart AI Platform
=======================================================================================
Provides modern typography (Plus Jakarta Sans, JetBrains Mono), glassmorphic card
surfaces, responsive layouts, micro-animations, and high-contrast fintech badges.
"""

import streamlit as st


def inject_custom_css() -> None:
    """Inject custom Google Fonts and comprehensive CSS design tokens into the Streamlit app."""
    custom_css = """
    <style>
    /* ── 1. Google Fonts ─────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    :root {
        --tm-primary: #6366f1;
        --tm-primary-dark: #4f46e5;
        --tm-primary-light: #818cf8;
        --tm-primary-glow: rgba(99, 102, 241, 0.25);
        --tm-accent-purple: #8b5cf6;
        --tm-accent-cyan: #06b6d4;
        --tm-success: #10b981;
        --tm-success-bg: rgba(16, 185, 129, 0.12);
        --tm-warning: #f59e0b;
        --tm-warning-bg: rgba(245, 158, 11, 0.12);
        --tm-danger: #f43f5e;
        --tm-danger-bg: rgba(244, 63, 94, 0.12);
        --tm-bg-card: rgba(30, 41, 59, 0.7);
        --tm-bg-surface: rgba(15, 23, 42, 0.85);
        --tm-border-light: rgba(148, 163, 184, 0.16);
        --tm-border-accent: rgba(99, 102, 241, 0.35);
        --tm-text-main: #f8fafc;
        --tm-text-muted: #94a3b8;
        --tm-font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        --tm-font-mono: 'JetBrains Mono', monospace;
    }

    /* ── 2. Global Typography & Resets ───────────────────────────── */
    html, body, [class*="css"], .stMarkdown, .stText, p, span, label {
        font-family: var(--tm-font-sans) !important;
        letter-spacing: -0.01em;
    }

    code, pre, .stCodeBlock {
        font-family: var(--tm-font-mono) !important;
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: var(--tm-font-sans) !important;
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
    }

    /* ── 3. App Header Bar ───────────────────────────────────────── */
    .tm-top-bar {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--tm-border-light);
        border-radius: 14px;
        padding: 14px 22px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    }

    .tm-brand-title {
        font-size: 22px;
        font-weight: 800;
        background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .tm-brand-tag {
        font-size: 10px;
        font-weight: 700;
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        padding: 3px 9px;
        border-radius: 20px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        display: inline-block;
    }

    .tm-badge-group {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
    }

    .tm-status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 11px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid var(--tm-border-light);
        color: var(--tm-text-muted);
    }

    .tm-pulse-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #10b981;
        box-shadow: 0 0 8px #10b981;
        animation: tm-pulse 2s infinite;
    }

    @keyframes tm-pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1.1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* ── 4. Badges & Tags ────────────────────────────────────────── */
    .tm-pill-ai {
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.22) 0%, rgba(99, 102, 241, 0.28) 100%);
        border: 1px solid rgba(139, 92, 246, 0.45);
        color: #c4b5fd !important;
        padding: 3px 10px;
        border-radius: 16px;
        font-size: 11px;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 5px;
        letter-spacing: 0.3px;
    }

    .tm-pill-customer {
        background: rgba(14, 165, 233, 0.18);
        border: 1px solid rgba(14, 165, 233, 0.4);
        color: #7dd3fc !important;
        padding: 3px 10px;
        border-radius: 16px;
        font-size: 11px;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }

    .tm-pill-stock-high {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.35);
        color: #6ee7b7 !important;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
    }

    .tm-pill-stock-low {
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid rgba(245, 158, 11, 0.35);
        color: #fcd34d !important;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
    }

    .tm-pill-stock-out {
        background: rgba(244, 63, 94, 0.15);
        border: 1px solid rgba(244, 63, 94, 0.35);
        color: #fda4af !important;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
    }

    /* ── 5. Agentic Flow Visualization ───────────────────────────── */
    .tm-understanding-box {
        background: linear-gradient(135deg, rgba(30, 27, 75, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(139, 92, 246, 0.35);
        border-left: 4px solid #8b5cf6;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 20px rgba(139, 92, 246, 0.1);
    }

    .tm-search-box {
        background: linear-gradient(135deg, rgba(12, 74, 110, 0.5) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(14, 165, 233, 0.35);
        border-left: 4px solid #0284c7;
        border-radius: 10px;
        padding: 10px 16px;
        margin-bottom: 14px;
        box-shadow: 0 4px 20px rgba(2, 132, 199, 0.1);
    }

    .tm-blocked-box {
        background: linear-gradient(135deg, rgba(88, 28, 45, 0.5) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(244, 63, 94, 0.4);
        border-left: 4px solid #e11d48;
        border-radius: 10px;
        padding: 12px 16px;
        margin-top: 10px;
        margin-bottom: 12px;
        box-shadow: 0 4px 20px rgba(225, 29, 72, 0.1);
    }

    .tm-guardrail-banner {
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.5) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(16, 185, 129, 0.35);
        border-left: 4px solid #10b981;
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 14px;
    }

    /* ── 6. Recommendation & Product Cards ───────────────────────── */
    .tm-product-card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }

    .tm-product-title {
        font-size: 16px;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 6px;
        line-height: 1.35;
    }

    .tm-product-price {
        font-family: var(--tm-font-mono);
        font-size: 18px;
        font-weight: 700;
        color: #38bdf8;
    }

    .tm-why-point {
        display: flex;
        align-items: flex-start;
        gap: 7px;
        font-size: 12px;
        color: #cbd5e1;
        margin-bottom: 4px;
        line-height: 1.4;
    }

    .tm-why-icon {
        color: #10b981;
        font-weight: 700;
        font-size: 13px;
        flex-shrink: 0;
    }

    .tm-upsell-container {
        background: linear-gradient(135deg, rgba(88, 28, 135, 0.3) 0%, rgba(30, 41, 59, 0.65) 100%);
        border: 1px solid rgba(168, 85, 247, 0.35);
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 10px;
    }

    /* ── 7. Merchant KPI Metric Cards ────────────────────────────── */
    .tm-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 14px;
        margin-bottom: 18px;
    }

    .tm-kpi-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid var(--tm-border-light);
        border-top: 3px solid var(--tm-primary);
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }

    .tm-kpi-card:hover {
        transform: translateY(-2px);
        border-color: var(--tm-border-accent);
    }

    .tm-kpi-label {
        font-size: 11px;
        font-weight: 600;
        color: var(--tm-text-muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .tm-kpi-value {
        font-family: var(--tm-font-mono);
        font-size: 26px;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.5px;
    }

    .tm-kpi-sub {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 4px;
    }

    /* ── 8. Streamlit Button & Widget Polish ──────────────────────── */
    div.stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        letter-spacing: -0.01em !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        border: 1px solid rgba(148, 163, 184, 0.2) !important;
    }

    div.stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25) !important;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
        border: 1px solid rgba(129, 140, 248, 0.4) !important;
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35) !important;
    }

    div.stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%) !important;
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5) !important;
    }

    /* Streamlit Containers styling */
    div[data-testid="stVerticalBlock"] > div[data-testid="stContainer"] {
        background: rgba(30, 41, 59, 0.4);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 12px;
        padding: 4px;
        transition: border-color 0.2s ease;
    }

    div[data-testid="stVerticalBlock"] > div[data-testid="stContainer"]:hover {
        border-color: rgba(99, 102, 241, 0.25);
    }

    /* Custom Scrollbars */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: rgba(15, 23, 42, 0.5);
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.25);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(148, 163, 184, 0.4);
    }

    /* Tab Styling */
    button[data-baseweb="tab"] {
        font-size: 13px !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        border-radius: 8px 8px 0 0 !important;
    }

    /* Hero Banner */
    .tm-hero-container {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(49, 46, 129, 0.35) 50%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 16px;
        padding: 22px 26px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
    }

    .tm-hero-title {
        font-size: 24px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .tm-hero-sub {
        font-size: 13px;
        color: #94a3b8;
        line-height: 1.6;
        max-width: 840px;
    }

    .tm-category-pills {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 14px;
    }

    .tm-category-pill {
        font-size: 11px;
        font-weight: 600;
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(148, 163, 184, 0.2);
        color: #cbd5e1;
        padding: 4px 12px;
        border-radius: 20px;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)


def render_header_bar(active_view: str = "customer") -> None:
    """Render the top brand navigation bar with live status indicators."""
    st.markdown(
        """
        <div class="tm-top-bar">
            <div class="tm-brand-title">
                <span>🛒 TechMart</span>
                <span class="tm-brand-tag">AI Commerce</span>
            </div>
            <div class="tm-badge-group">
                <div class="tm-status-pill">
                    <span class="tm-pulse-dot"></span>
                    <span>AI Shopping Agent: Online</span>
                </div>
                <div class="tm-status-pill">
                    <span style="color:#10b981;">🛡️</span>
                    <span>Guardrails: Enforced</span>
                </div>
                <div class="tm-status-pill">
                    <span style="color:#38bdf8;">💳</span>
                    <span>Razorpay: Sandbox Ready</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero_banner() -> None:
    """Render the customer discovery hero banner with category chips."""
    st.markdown(
        """
        <div class="tm-hero-container">
            <div class="tm-hero-title">
                <span>Find the Perfect Tech for Your Workflow & Budget</span>
            </div>
            <div class="tm-hero-sub">
                Conversational AI shopping grounded in live SQLite catalog. Ask naturally in plain English:
                <i>"Laptop for coding under 70000"</i> or <i>"Smartphone under 25000 with AMOLED"</i>.
                Automatic stock deduction, fintech pre-payment safety guardrails, and Razorpay checkout.
            </div>
            <div class="tm-category-pills">
                <span class="tm-category-pill">💻 Laptops</span>
                <span class="tm-category-pill">📱 Smartphones</span>
                <span class="tm-category-pill">🎧 Headphones</span>
                <span class="tm-category-pill">🖥️ Monitors</span>
                <span class="tm-category-pill">⌨️ Keyboards</span>
                <span class="tm-category-pill">🖱️ Mice</span>
                <span class="tm-category-pill">⌚ Smartwatches</span>
                <span class="tm-category-pill">🔋 Power Banks</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_agent_understanding(understanding: dict) -> None:
    """Render the agent understanding chip panel."""
    category = understanding.get("category", "All Categories")
    budget = understanding.get("budget", "None")
    purpose = understanding.get("purpose", "General Use")
    prefs = understanding.get("preferences", "None")

    st.markdown(
        f"""
        <div class="tm-understanding-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-weight:800; font-size:12px; color:#c4b5fd; letter-spacing:0.5px;">🤖 AGENT INTENT RECOGNITION</span>
                <span class="tm-pill-ai">NLP Model</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:8px; font-size:12px; color:#e2e8f0;">
                <span style="background:rgba(15,23,42,0.6); padding:3px 10px; border-radius:6px; border:1px solid rgba(148,163,184,0.2);"><b>Category:</b> {category}</span>
                <span style="background:rgba(15,23,42,0.6); padding:3px 10px; border-radius:6px; border:1px solid rgba(148,163,184,0.2);"><b>Budget:</b> {budget}</span>
                <span style="background:rgba(15,23,42,0.6); padding:3px 10px; border-radius:6px; border:1px solid rgba(148,163,184,0.2);"><b>Purpose:</b> {purpose}</span>
                <span style="background:rgba(15,23,42,0.6); padding:3px 10px; border-radius:6px; border:1px solid rgba(148,163,184,0.2);"><b>Preferences:</b> {prefs}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_catalog_search(catalog_search: dict) -> None:
    """Render catalog search statistics card."""
    evaluated = catalog_search.get("products_evaluated", 0)
    matching = catalog_search.get("products_matching", 0)

    st.markdown(
        f"""
        <div class="tm-search-box">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:800; font-size:12px; color:#38bdf8; letter-spacing:0.5px;">🔎 SQLITE CATALOG VERIFICATION</span>
                <span style="font-size:12px; color:#bae6fd;">
                    Evaluated: <b>{evaluated}</b> &nbsp;|&nbsp; Matches: <b>{matching}</b>
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_guardrail_blocked(blocked_candidates: list) -> None:
    """Render blocked items due to budget or stock safety rules."""
    for blocked in blocked_candidates:
        st.markdown(
            f"""
            <div class="tm-blocked-box">
                <div style="font-weight:800; font-size:12px; color:#fda4af; margin-bottom:4px; letter-spacing:0.5px;">🛡️ GUARDRAIL INTERCEPTION</div>
                <div style="font-size:12px; color:#fecdd3; line-height:1.5;">
                    {blocked.get('reason', '')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_guardrails_sidebar_panel() -> None:
    """Render the active safety guardrails panel in the sidebar."""
    st.markdown(
        """
        <div class="tm-guardrail-banner">
            <div style="font-weight:800; font-size:12px; color:#6ee7b7; margin-bottom:6px; letter-spacing:0.5px;">🛡️ FINTECH SAFETY GUARDRAILS</div>
            <div style="font-size:11px; color:#a7f3d0; line-height:1.6;">
                ✓ Explicit customer approval required<br>
                ✓ Budget limit strictly enforced<br>
                ✓ Product must exist in catalog<br>
                ✓ Real-time stock verified & reserved<br>
                ✓ Cross-sell requires explicit consent<br>
                ✓ Payment requires 3D-Secure approval
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card_html(title: str, value: str, sub: str = "", border_color: str = "#6366f1") -> str:
    """Return HTML string for a polished merchant KPI card."""
    return f"""
    <div class="tm-kpi-card" style="border-top-color: {border_color};">
        <div class="tm-kpi-label">{title}</div>
        <div class="tm-kpi-value">{value}</div>
        {f'<div class="tm-kpi-sub">{sub}</div>' if sub else ''}
    </div>
    """
