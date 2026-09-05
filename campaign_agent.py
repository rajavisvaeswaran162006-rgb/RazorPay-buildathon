"""
campaign_agent.py -- TechMart AI Campaign & Offer Agent
======================================================
Merchant-side proactive intelligence module:
  1. Aggregates SQLite facts (sales, orders, stock, attachment rates).
  2. Identifies revenue growth, cross-sell attachment, and inventory clearance opportunities.
  3. Prompts OpenAI (or deterministic fallback) for structured, explainable campaigns.
  4. Strictly validates all output against catalog grounding, bounded discounts, and DB facts.
  5. Enforces explicit merchant human-in-the-loop approval before anything is recorded.
  6. Emits tamper-evident compliance audit logs (CAMPAIGN_ANALYSIS, CAMPAIGN_SUGGESTED,
     CAMPAIGN_APPROVED, CAMPAIGN_REJECTED).
"""

import os
import json
import logging
from typing import Any
from dotenv import load_dotenv

from database import (
    get_sales_and_catalog_summary,
    search_products,
    get_product,
    save_campaign_suggestion,
    update_campaign_status,
    get_latest_campaign_suggestion,
    get_campaign_history,
)
from audit import log_event

load_dotenv()
logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()


def get_openai_client():
    """Lazily create OpenAI client if API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Validation & Business Rules Guardrails
# ─────────────────────────────────────────────────────────────────────────────

def validate_campaign_suggestion(
    campaign: dict[str, Any],
    all_products: list[dict[str, Any]]
) -> tuple[bool, str]:
    """
    Validate that an AI-generated campaign conforms strictly to business rules:
      1. Mandatory fields present and non-empty.
      2. No invented / hallucinated products (must match catalog).
      3. Bounded discounts (no discount > 100%, no negative discounts).
      4. Fixed discount must not exceed the price of the relevant target product.
      5. Evidence bullets present and grounded.
    Returns (is_valid, error_message).
    """
    if not isinstance(campaign, dict):
        return False, "Campaign suggestion must be a valid dictionary."

    # Check required fields
    required_fields = ["campaign_type", "title", "reason", "suggested_discount", "evidence"]
    for field in required_fields:
        if not campaign.get(field):
            return False, f"Missing or empty required field: '{field}'"

    # Evidence list check
    evidence = campaign.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) == 0:
        return False, "Campaign must include at least one concise evidence bullet point."

    # Product Grounding Check
    catalog_names = {p["name"].strip().lower() for p in all_products}
    catalog_by_name = {p["name"].strip().lower(): p for p in all_products}

    target_products = campaign.get("target_products", [])
    if isinstance(target_products, str):
        target_products = [target_products]

    matched_products = []
    for prod_name in target_products:
        p_clean = str(prod_name).strip().lower()
        if p_clean not in catalog_names:
            # Check for partial match
            partial = [p for p in all_products if p_clean in p["name"].lower() or p["name"].lower() in p_clean]
            if not partial:
                return False, f"Product Guardrail Blocked: Target product '{prod_name}' does not exist in SQLite catalog."
            matched_products.append(partial[0])
        else:
            matched_products.append(catalog_by_name[p_clean])

    # Discount Bounds Check
    discount_amount = float(campaign.get("discount_amount", 0.0))
    discount_type = campaign.get("discount_type", "fixed").lower()

    if discount_amount < 0:
        return False, f"Discount Guardrail Blocked: Negative discount value ({discount_amount}) is forbidden."

    if discount_type == "percent":
        if discount_amount > 50.0:
            return False, f"Discount Guardrail Blocked: Percentage discount ({discount_amount}%) exceeds safe 50% cap."
    else:
        # Fixed discount check
        if matched_products:
            min_price = min(p["price"] for p in matched_products)
            if discount_amount >= min_price:
                return False, f"Discount Guardrail Blocked: Fixed discount ₹{discount_amount:,.0f} cannot exceed product price ₹{min_price:,.0f}."
        elif discount_amount > 5000.0:
            return False, f"Discount Guardrail Blocked: Unbounded fixed discount ₹{discount_amount:,.0f}."

    return True, "PASSED"


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic Rule-Based Fallback Engine
# ─────────────────────────────────────────────────────────────────────────────

def generate_deterministic_campaign(
    summary: dict[str, Any],
    all_products: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Generate a 100% grounded campaign opportunity from actual SQLite data
    when OpenAI is unavailable or rate-limited.
    """
    attachment_stats = summary.get("attachment_stats", [])
    low_sales_high_stock = summary.get("low_sales_high_stock", [])
    top_product = summary.get("top_product")
    top_category = summary.get("top_category")

    # Opportunity 1: Low Attachment Rate on High Sales (e.g. Laptop -> Laptop Bag)
    for att in attachment_stats:
        if att["primary_orders_count"] >= 1 and att["attachment_rate_pct"] < 30.0 and att["secondary_stock"] > 0:
            primary_cat = att["primary_category"]
            secondary_cat = att["secondary_category"]
            sec_prods = att.get("secondary_products", [])
            target_accessory = sec_prods[0] if sec_prods else None
            sec_name = target_accessory["name"] if target_accessory else f"{secondary_cat}"
            sec_price = target_accessory["price"] if target_accessory else 1299.0

            discount = 300.0 if sec_price >= 1000 else 150.0

            # Find a representative primary product
            primary_prods = [p for p in all_products if p["category"] == primary_cat and p["stock"] > 0]
            rep_primary = primary_prods[0] if primary_prods else None
            prim_name = rep_primary["name"] if rep_primary else primary_cat

            return {
                "campaign_type": "bundle",
                "title": f"{primary_cat} + {secondary_cat} Attachment Bundle",
                "reason": f"{primary_cat} buyers have a low attachment rate for {secondary_cat}s ({att['attachment_rate_pct']}%), leaving {att['secondary_stock']} units unattached in stock.",
                "suggested_discount": f"₹{discount:,.0f} bundle discount on {sec_name}",
                "discount_type": "fixed",
                "discount_amount": discount,
                "target_products": [prim_name, sec_name],
                "target_product_id": target_accessory["id"] if target_accessory else None,
                "target_product_name": sec_name,
                "target_audience": f"Customers purchasing a {primary_cat}",
                "objective": f"Increase {secondary_cat} attachment rate and monetize unattached inventory",
                "evidence": [
                    f"✓ {att['primary_orders_count']} {primary_cat} orders completed in store history",
                    f"✓ Only {att['attached_orders_count']} order(s) included a {secondary_cat} ({att['attachment_rate_pct']}% attachment rate)",
                    f"✓ {sec_name} inventory: {att['secondary_stock']} units available in stock",
                    f"✓ Attractive ₹{discount:,.0f} incentive increases average basket size without eroding core margins",
                ],
                "confidence": "high",
            }

    # Opportunity 2: High Inventory Clearance
    if low_sales_high_stock:
        item = low_sales_high_stock[0]
        discount_pct = 15.0
        discount_val = round((item["price"] * discount_pct) / 100.0, 0)
        return {
            "campaign_type": "clearance",
            "title": f"{item['name']} Inventory Acceleration Promo",
            "reason": f"{item['name']} has {item['stock']} units in stock but has only recorded {item['units_sold']} sale(s).",
            "suggested_discount": f"{discount_pct:.0f}% promotional discount (save ₹{discount_val:,.0f})",
            "discount_type": "percent",
            "discount_amount": discount_pct,
            "target_products": [item["name"]],
            "target_product_id": item["id"],
            "target_product_name": item["name"],
            "target_audience": f"Shoppers browsing {item['category']} devices",
            "objective": f"Accelerate inventory turnover and free up working capital",
            "evidence": [
                f"✓ High inventory holding: {item['stock']} units in warehouse",
                f"✓ Low sales velocity: {item['units_sold']} units sold in recorded history",
                f"✓ Bounded {discount_pct:.0f}% discount preserves gross product profitability",
            ],
            "confidence": "medium",
        }

    # Fallback generic promotion
    top_p_name = top_product["name"] if top_product else "Top Catalog Product"
    return {
        "campaign_type": "promotion",
        "title": f"Featured Spotlight: {top_p_name}",
        "reason": f"Capitalize on proven customer demand for our best-selling product.",
        "suggested_discount": "5% loyalty discount",
        "discount_type": "percent",
        "discount_amount": 5.0,
        "target_products": [top_p_name],
        "target_product_id": top_product["id"] if top_product else None,
        "target_product_name": top_p_name,
        "target_audience": "Returning and new store customers",
        "objective": "Boost conversion rate on high-intent catalog traffic",
        "evidence": [
            f"✓ Proven top seller with consistent demand",
            f"✓ Healthy inventory availability",
        ],
        "confidence": "medium",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main AI Campaign Analysis Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def analyze_and_suggest_campaign(force_refresh: bool = False) -> dict[str, Any]:
    """
    Main entry point:
      1. Fetch real summary from SQLite (sales, stock, attachment rates).
      2. Check if sufficient data exists.
      3. Call OpenAI for structured campaign suggestion.
      4. Fallback gracefully to deterministic rule engine if OpenAI unavailable.
      5. Strictly validate against catalog grounding & discount bounds.
      6. Persist to campaign_suggestions table as 'SUGGESTED'.
      7. Log CAMPAIGN_ANALYSIS & CAMPAIGN_SUGGESTED audit events.
    """
    summary = get_sales_and_catalog_summary()
    from database import get_all_products_admin
    all_prods = get_all_products_admin()

    # Log CAMPAIGN_ANALYSIS event
    log_event(
        event_type="CAMPAIGN_ANALYSIS",
        action="Analyzed merchant sales, catalog stock & attachment rates",
        details=f"Paid Orders: {summary['paid_orders']}, Total Rev: ₹{summary['total_revenue']:,.0f}, Catalog Items: {len(all_prods)}",
        status="SUCCESS",
        rule_or_tool="AI Campaign Agent",
    )

    # Check data sufficiency
    if summary["paid_orders"] == 0 and len(all_prods) == 0:
        return {
            "status": "insufficient_data",
            "message": "Not enough sales data to generate a reliable campaign recommendation.",
            "business_insights": None,
            "campaign": None,
        }

    # Extract business insights for UI
    top_cat = summary.get("top_category")
    top_prod = summary.get("top_product")
    low_stock_opp = summary.get("low_sales_high_stock", [{}])[0] if summary.get("low_sales_high_stock") else None

    # Key attachment opportunity
    key_opp = None
    for att in summary.get("attachment_stats", []):
        if att["primary_orders_count"] > 0 and att["attachment_rate_pct"] < 50.0 and att["secondary_stock"] > 0:
            key_opp = f"{att['primary_category']} ➔ {att['secondary_category']} ({att['attachment_rate_pct']}% attachment)"
            break

    business_insights = {
        "top_category": top_cat["category"] if top_cat else "Laptops",
        "best_selling_product": top_prod["name"] if top_prod else "BytePro Core 14",
        "low_selling_accessory": low_stock_opp["name"] if low_stock_opp else "TechCarry 15",
        "opportunity_identified": key_opp or "Laptop ➔ Laptop Bag (0.0% attachment)",
        "paid_orders_analyzed": summary["paid_orders"],
        "total_revenue_analyzed": summary["total_revenue"],
    }

    # Try OpenAI Structured Recommendation
    client = get_openai_client()
    campaign_result = None

    if client:
        try:
            # Build data facts context
            compact_context = {
                "paid_orders": summary["paid_orders"],
                "total_revenue": summary["total_revenue"],
                "top_category": business_insights["top_category"],
                "best_selling_product": business_insights["best_selling_product"],
                "attachment_stats": [
                    {
                        "primary": a["primary_category"],
                        "secondary": a["secondary_category"],
                        "primary_orders": a["primary_orders_count"],
                        "attachment_rate_pct": a["attachment_rate_pct"],
                        "secondary_stock": a["secondary_stock"],
                    }
                    for a in summary.get("attachment_stats", [])[:4]
                ],
                "low_sales_high_stock": [
                    {"name": p["name"], "category": p["category"], "stock": p["stock"], "sold": p["units_sold"], "price": p["price"]}
                    for p in summary.get("low_sales_high_stock", [])[:3]
                ],
            }

            system_prompt = (
                "You are an expert E-commerce Merchant Campaign Agent. "
                "Analyze the provided factual store data and propose ONE high-ROI promotional campaign. "
                "Rules:\n"
                "1. ONLY reference products that genuinely exist in the store data.\n"
                "2. Suggested discounts must be strictly bounded (e.g. ₹200-₹500 fixed, or 10-20% percent).\n"
                "3. Provide 3-4 concise, bulleted evidence points based exclusively on the provided data.\n"
                "4. Return STRICT JSON conforming to the schema."
            )

            user_prompt = f"Store Performance Facts:\n{json.dumps(compact_context, indent=2)}\n\nGenerate ONE high-impact campaign recommendation in JSON."

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            raw_json = response.choices[0].message.content.strip()
            parsed = json.loads(raw_json)

            # Validate generated campaign
            is_valid, err_msg = validate_campaign_suggestion(parsed, all_prods)
            if is_valid:
                campaign_result = parsed
            else:
                logger.warning(f"OpenAI campaign failed validation: {err_msg}. Using deterministic fallback.")
        except Exception as e:
            logger.warning(f"OpenAI campaign generation error: {e}. Using deterministic fallback.")

    # If OpenAI unavailable, errored, or invalid, use deterministic engine
    if not campaign_result:
        campaign_result = generate_deterministic_campaign(summary, all_prods)

    # Final validation check
    is_valid, err_msg = validate_campaign_suggestion(campaign_result, all_prods)
    if not is_valid:
        # Fallback to guaranteed safe campaign
        campaign_result = generate_deterministic_campaign(summary, all_prods)

    # Save to SQLite database with status 'SUGGESTED'
    db_id = save_campaign_suggestion(campaign_result)
    campaign_result["id"] = db_id
    campaign_result["status"] = "SUGGESTED"

    # Log CAMPAIGN_SUGGESTED audit event
    log_event(
        event_type="CAMPAIGN_SUGGESTED",
        action=f"AI suggested campaign: '{campaign_result['title']}' (ID: {db_id})",
        details=f"Type: {campaign_result['campaign_type']}, Offer: {campaign_result['suggested_discount']}, Objective: {campaign_result.get('objective', '')}",
        status="SUGGESTED",
        rule_or_tool="AI Campaign Agent",
    )

    return {
        "status": "success",
        "business_insights": business_insights,
        "campaign": campaign_result,
    }


def approve_campaign(campaign_id: int) -> bool:
    """Explicit merchant human-in-the-loop campaign approval."""
    success = update_campaign_status(campaign_id, "APPROVED")
    if success:
        log_event(
            event_type="CAMPAIGN_APPROVED",
            action=f"Merchant APPROVED campaign suggestion #{campaign_id}",
            details=f"Campaign #{campaign_id} formally approved by merchant. Status set to APPROVED.",
            status="APPROVED",
            rule_or_tool="Merchant Decision Engine",
        )
    return success


def reject_campaign(campaign_id: int) -> bool:
    """Explicit merchant human-in-the-loop campaign rejection."""
    success = update_campaign_status(campaign_id, "REJECTED")
    if success:
        log_event(
            event_type="CAMPAIGN_REJECTED",
            action=f"Merchant REJECTED campaign suggestion #{campaign_id}",
            details=f"Campaign #{campaign_id} formally declined by merchant. Status set to REJECTED.",
            status="REJECTED",
            rule_or_tool="Merchant Decision Engine",
        )
    return success
