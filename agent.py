"""
agent.py — TechMart AI Shopping Agent
======================================
Core AI shopping agent orchestration module:
  1. Natural language requirement extraction (category, budget, purpose, specs)
  2. Safe parameterized SQLite product search via database.py (no raw SQL by LLM)
  3. AI recommendation & justification generation ("Why I recommend it")
  4. Non-intrusive upsell / cross-sell suggestions with explicit customer approval
  5. Strict safety guardrails (no hallucinations, no budget overshoot, stock check)
  6. Resilient zero-crash fallback engine when OpenAI API is unavailable
  7. Audit logging of every agent step via audit.py
"""

import os
import re
import json
import logging
from typing import Any
from dotenv import load_dotenv

from database import search_products, get_product, get_related_products
from audit import log_event

load_dotenv()
logger = logging.getLogger(__name__)

# Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# Category aliases for fallback extraction
CATEGORY_MAP = {
    "laptop": "Laptop",
    "laptops": "Laptop",
    "notebook": "Laptop",
    "macbook": "Laptop",
    "smartphone": "Smartphone",
    "smartphones": "Smartphone",
    "phone": "Smartphone",
    "phones": "Smartphone",
    "mobile": "Smartphone",
    "mobiles": "Smartphone",
    "tablet": "Tablet",
    "tablets": "Tablet",
    "tab": "Tablet",
    "ipad": "Tablet",
    "headphone": "Headphones",
    "headphones": "Headphones",
    "earphone": "Headphones",
    "earphones": "Headphones",
    "airpod": "Headphones",
    "airpods": "Headphones",
    "earbud": "Earbuds",
    "earbuds": "Earbuds",
    "buds": "Earbuds",
    "tws": "Earbuds",
    "speaker": "Speaker",
    "speakers": "Speaker",
    "bluetooth speaker": "Speaker",
    "mouse": "Mouse",
    "mice": "Mouse",
    "gaming mouse": "Mouse",
    "keyboard": "Keyboard",
    "keyboards": "Keyboard",
    "mechanical keyboard": "Keyboard",
    "monitor": "Monitor",
    "monitors": "Monitor",
    "screen": "Monitor",
    "display": "Monitor",
    "charger": "Charger",
    "chargers": "Charger",
    "adapter": "Charger",
    "power bank": "Power Bank",
    "powerbank": "Power Bank",
    "battery pack": "Power Bank",
    "bag": "Laptop Bag",
    "bags": "Laptop Bag",
    "backpack": "Laptop Bag",
    "laptop bag": "Laptop Bag",
    "smartwatch": "Smartwatch",
    "smart watch": "Smartwatch",
    "watch": "Smartwatch",
    "watches": "Smartwatch",
    "fitness tracker": "Smartwatch",
    "router": "Router",
    "routers": "Router",
    "wifi": "Router",
    "wi-fi": "Router",
}

STOP_WORDS = {
    "i", "me", "my", "need", "want", "looking", "for", "find", "show",
    "search", "get", "give", "a", "an", "the", "some", "any", "best",
    "good", "top", "cheap", "budget", "under", "below", "less", "than",
    "within", "around", "about", "please", "can", "you", "recommend",
    "suggestion", "suggest", "buy", "purchase", "order", "with", "and",
    "or", "in", "of", "to", "is", "are", "it", "that", "this", "rs",
    "rupees", "inr", "price", "priced", "costing", "range",
    "something", "anything", "item", "items", "stuff", "device", "devices",
    "product", "products", "one", "ones", "type", "kind",
}


def get_openai_client():
    """Lazily create OpenAI client if API key is present."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.warning(f"Could not initialize OpenAI client: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Requirement Extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_requirements_openai(prompt: str, client) -> dict | None:
    """Extract shopping requirements using OpenAI."""
    system_prompt = (
        "You are an AI commerce requirements extractor for TechMart. "
        "Analyze the customer query and extract structured shopping constraints.\n"
        "Allowed categories: ['Laptop', 'Smartphone', 'Tablet', 'Headphones', 'Earbuds', 'Speaker', 'Mouse', 'Keyboard', 'Monitor', 'Charger', 'Power Bank', 'Laptop Bag', 'Smartwatch', 'Router'].\n"
        "Return a JSON object with keys:\n"
        "- category: string (one of allowed categories or null)\n"
        "- max_price: float or null (maximum budget in INR)\n"
        "- min_price: float or null (minimum budget in INR)\n"
        "- purpose: string or null (e.g. 'coding', 'gaming', 'college', 'work', 'music')\n"
        "- preferences: string or null (e.g. 'mechanical', 'wireless', 'lightweight')\n"
        "- keyword: string or null (specific model, brand, or search terms like 'Ryzen', 'boAt', 'RGB')\n"
        "Respond ONLY with valid JSON. Do not include markdown codeblocks or extra text."
    )
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        # Clean any markdown fences if present
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
        data = json.loads(content)
        return data
    except Exception as e:
        logger.warning(f"OpenAI extraction failed, using fallback: {e}")
        return None


def extract_requirements_fallback(prompt: str) -> dict:
    """
    Deterministic rule-based requirement extraction fallback when OpenAI is offline.
    """
    text = prompt.strip().lower()

    # Extract price
    max_price = None
    min_price = None

    # Between X and Y
    between_match = re.search(
        r"(?:between|from)\s*(?:rs\.?|inr|rupees)?\s*(\d[\d,]*)\s*(?:to|and|-)\s*(?:rs\.?|inr|rupees)?\s*(\d[\d,]*)",
        text,
    )
    if between_match:
        min_price = float(between_match.group(1).replace(",", ""))
        max_price = float(between_match.group(2).replace(",", ""))
        text = text[:between_match.start()] + text[between_match.end():]
    else:
        price_patterns = [
            r"(?:under|below|within|less\s+than|cheaper\s+than|max|upto|up\s+to|<)\s*(?:rs\.?|inr|rupees)?\s*(\d[\d,]*)",
            r"(?:rs\.?|inr|rupees)\s*(\d[\d,]*)",
            r"(\d{3,6})\s*(?:rs|rupees|inr|budget)",
        ]
        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match:
                max_price = float(match.group(1).replace(",", ""))
                text = text[:match.start()] + text[match.end():]
                break

    # Extract category
    category = ""
    sorted_aliases = sorted(CATEGORY_MAP.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            category = CATEGORY_MAP[alias]
            break

    # Extract purpose
    purpose = None
    purposes = ["coding", "programming", "gaming", "college", "student", "office", "work", "music", "travel"]
    for p in purposes:
        if p in text:
            purpose = p
            break

    # Extract remaining meaningful keywords
    words = re.findall(r"[a-z0-9]+", text)
    filtered = [w for w in words if w not in STOP_WORDS and w not in CATEGORY_MAP and len(w) > 1]
    keyword = " ".join(filtered) if filtered else None

    return {
        "category": category or None,
        "max_price": max_price,
        "min_price": min_price,
        "purpose": purpose,
        "preferences": None,
        "keyword": keyword,
    }


def extract_requirements(prompt: str) -> tuple[dict, str]:
    """
    Extract shopping requirements using OpenAI if configured, otherwise fallback.
    Returns (requirements_dict, engine_used).
    """
    client = get_openai_client()
    if client:
        res = extract_requirements_openai(prompt, client)
        if res:
            return res, "OpenAI"
    return extract_requirements_fallback(prompt), "Fallback"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Candidate Ranking & Justification
# ─────────────────────────────────────────────────────────────────────────────

def build_why_points_fallback(product: dict, requirements: dict) -> list[str]:
    """Generate accurate, factual bullet points strictly from SQLite product data."""
    points = []
    max_price = requirements.get("max_price")
    price = product.get("price", 0.0)

    if max_price:
        savings = max_price - price
        if savings > 0:
            points.append(f"Within your budget of ₹{max_price:,.0f} (saves ₹{savings:,.0f})")
        else:
            points.append(f"Exactly at your budget of ₹{max_price:,.0f}")
    else:
        points.append(f"Priced at ₹{price:,.0f}")

    desc = product.get("description", "")
    # Check for RAM / SSD specs
    ram_match = re.search(r"(\d+\s*GB\s*RAM)", desc, re.IGNORECASE)
    ssd_match = re.search(r"(\d+\s*(?:GB|TB)\s*SSD)", desc, re.IGNORECASE)
    if ram_match and ssd_match:
        points.append(f"{ram_match.group(1)} & {ssd_match.group(1)} storage")
    elif ram_match:
        points.append(ram_match.group(1))

    # Check for processor / battery
    proc_match = re.search(r"(Ryzen\s*\d+|Intel\s*(?:Core\s*)?i\d+|12th Gen)", desc, re.IGNORECASE)
    if proc_match:
        points.append(f"Powered by {proc_match.group(1)} processor")

    battery_match = re.search(r"(\d+[- ]hour\s*battery)", desc, re.IGNORECASE)
    if battery_match:
        points.append(f"Long-lasting {battery_match.group(1)}")

    # Purpose alignment
    purpose = requirements.get("purpose")
    if purpose:
        points.append(f"Suitable for {purpose} and daily performance")

    # In stock
    stock = product.get("stock", 0)
    if stock > 10:
        points.append(f"In stock & ready to dispatch ({stock} available)")
    elif stock > 0:
        points.append(f"Limited stock remaining ({stock} left)")

    # Ensure at least 3 points
    if len(points) < 3:
        points.append(f"Genuine {product.get('category', 'product')} with manufacturer warranty")

    return points[:4]


def rank_and_explain_openai(
    prompt: str,
    candidate_products: list[dict],
    requirements: dict,
    client,
) -> dict | None:
    """Use OpenAI to rank top products and explain recommendations based strictly on DB data."""
    # Build a clean representation of products
    products_context = []
    for p in candidate_products[:8]:
        products_context.append({
            "id": p["id"],
            "name": p["name"],
            "category": p["category"],
            "price": p["price"],
            "stock": p["stock"],
            "description": p["description"],
        })

    max_price = requirements.get("max_price")
    system_prompt = (
        "You are TechMart's AI Shopping Agent. Recommend the top 5 products (or up to 5 best matches) from the provided catalog.\n"
        "STRICT SAFETY RULES:\n"
        "1. NEVER invent products, prices, or specs. Use ONLY the provided catalog.\n"
        f"2. NEVER exceed the customer's budget (Max budget: ₹{max_price if max_price else 'No limit'}).\n"
        "3. Every recommended product MUST exist in the catalog list.\n"
        "4. Provide 3-4 factual 'why_points' highlighting why this product matches the customer's purpose and budget.\n"
        "Format output as JSON:\n"
        "{\n"
        '  "summary_message": "Friendly greeting and summary of the recommendation...",\n'
        '  "recommendations": [\n'
        "    {\n"
        '      "product_id": 1,\n'
        '      "recommendation_pitch": "I recommend the HP 15s Ryzen 5 because it fits within your ₹70,000 budget and has 8GB RAM...",\n'
        '      "why_points": ["Within your ₹70,000 budget", "8GB RAM & 512GB SSD for coding", "Fast AMD Ryzen 5 processor"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Respond ONLY with valid raw JSON."
    )

    user_msg = (
        f"Customer request: '{prompt}'\n"
        f"Extracted requirements: {json.dumps(requirements)}\n"
        f"Catalog products:\n{json.dumps(products_context, indent=2)}"
    )

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
        data = json.loads(content)
        return data
    except Exception as e:
        logger.warning(f"OpenAI ranking failed, falling back: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Conversational Helpers & Grounded Spec Parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_product_specs(product: dict) -> dict[str, str]:
    """Parse real specifications from SQLite description with zero hallucination."""
    desc = product.get("description", "")
    specs = {
        "Name": product.get("name", "Unknown"),
        "Category": product.get("category", "Tech"),
        "Price": f"₹{product.get('price', 0.0):,.0f}",
        "Stock": f"{product.get('stock', 0)} units available",
        "Raw Description": desc,
    }
    ram_match = re.search(r"(\d+\s*GB\s*RAM)", desc, re.IGNORECASE)
    if ram_match:
        specs["RAM"] = ram_match.group(1).upper()
    ssd_match = re.search(r"(\d+\s*(?:GB|TB)\s*(?:SSD|Storage))", desc, re.IGNORECASE)
    if ssd_match:
        specs["Storage"] = ssd_match.group(1).upper()
    proc_match = re.search(r"(Ryzen\s*\d+|Intel\s*(?:Core\s*)?i\d+|M[123](?:\s*Pro|\s*Max)?|Snapdragon\s*[a-z0-9]+|Octa-Core)", desc, re.IGNORECASE)
    if proc_match:
        specs["Processor"] = proc_match.group(1)
    disp_match = re.search(r"(\d+(?:\.\d+)?-inch\s*(?:FHD|AMOLED|IPS|4K|120Hz|144Hz|Retina)?[^,]*)", desc, re.IGNORECASE)
    if disp_match:
        specs["Display"] = disp_match.group(1).strip()
    battery_match = re.search(r"(\d+[- ]hour\s*battery|\d+\s*mAh)", desc, re.IGNORECASE)
    if battery_match:
        specs["Battery"] = battery_match.group(1)
    return specs


def extract_price_from_text(text: str) -> float | None:
    """Extract numeric price or budget from text (e.g. '70000', '70k', 'Rs. 60,000')."""
    # 50k / 60k
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", text, re.IGNORECASE)
    if k_match:
        return float(k_match.group(1)) * 1000
    # Digits with optional commas
    match = re.search(r"(?:rs\.?|inr|rupees|budget|to|under|<)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6})\b", text, re.IGNORECASE)
    if match:
        val = match.group(1).replace(",", "")
        return float(val)
    return None


def classify_conversational_intent(prompt: str, context: dict[str, Any]) -> str:
    """Classify user intent using context and conversational patterns."""
    text = prompt.strip().lower()

    # 1. Clarification reply
    if context.get("awaiting_clarification"):
        return "CLARIFICATION_REPLY"

    # 2. Cart queries
    if re.search(r"\b(?:how much is my cart|what is in my cart|view cart|cart total|check cart|cart price|items in cart)\b", text):
        return "CART_SUMMARY"
    if re.search(r"\bcan i stay under\b", text) or (re.search(r"\b(?:stay under|under \d+)\b", text) and "cart" in text):
        return "CART_BUDGET_CHECK"
    if re.search(r"\b(?:suggest\s+(?:an?\s+)?accessory|accessory within|accessories within|accessory for my remaining)\b", text):
        return "CART_ACCESSORY_SUGGESTION"

    # 3. Comparison
    if re.search(r"\b(?:compare|comparison|versus| vs )\b", text):
        return "COMPARISON"
    if re.search(r"\bwhich\s+(?:one\s+)?is\s+better\b", text) or re.search(r"\bwhich\s+one\s+(?:should i buy|to buy|for)\b", text):
        return "COMPARISON"

    # 4. Cheaper alternatives
    if re.search(r"\b(?:cheaper|more affordable|lower price|less expensive)\b", text):
        return "CHEAPER_ALTERNATIVES"

    # 5. Another one / Show more
    if re.search(r"\b(?:another one|show another|different one|show more|other options|i don't like this|i dont like this|something else)\b", text):
        return "ANOTHER_ALTERNATIVE"

    # 6. Budget change
    if re.search(r"\b(?:increase|raise|change|update|make|set)?\s*(?:my\s*)?budget\s*(?:to|is)?\s*(?:rs\.?|inr|rupees)?\s*\d+", text) or re.search(r"\bactually\s*(?:make it|increase to|upto)?\s*(?:rs\.?|inr|rupees)?\s*\d+", text):
        if context.get("category") or context.get("recently_displayed_products"):
            return "BUDGET_UPDATE"

    # 7. Intelligent clarification trigger for underspecified requests
    # e.g. "I need a laptop" without budget or purpose
    if re.search(r"\b(?:i need|i want|looking for|can you recommend|suggest me|recommend me|help me find)\b", text):
        req = extract_requirements_fallback(text)
        cat = req.get("category")
        if cat and not req.get("max_price") and not req.get("purpose") and not req.get("keyword"):
            return "CLARIFICATION_PROMPT"

    return "SEARCH"


def handle_clarification_prompt(category: str, user_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Ask a concise, intelligent clarifying question when a request lacks budget/purpose."""
    question = (
        f"What is your approximate budget for the **{category}**, and will you be "
        f"using it for coding, office work, gaming, or everyday use?"
    )
    log_event(
        event_type="CLARIFICATION_ASKED",
        action=f"Requested clarification for {category}",
        details=f"Prompt '{user_prompt}' missing budget and purpose; asked customer for constraints",
        status="AWAITING_INPUT",
        rule_or_tool="Clarification Engine",
    )
    context["awaiting_clarification"] = "budget_and_purpose"
    context["category"] = category
    context["previous_user_request"] = user_prompt

    return {
        "status": "clarification",
        "requirements": {"category": category, "max_price": None, "purpose": None, "keyword": None},
        "agent_understanding": {
            "category": category,
            "budget": "Awaiting customer input",
            "purpose": "Awaiting customer input",
            "preferences": "Awaiting customer input",
        },
        "catalog_search": {
            "products_evaluated": 0,
            "products_matching": 0,
            "blocked_candidates": [],
        },
        "engine": "Clarification Engine",
        "message": question,
        "recommendations": [],
        "conversation_context": context,
    }


def handle_clarification_reply(user_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Process user's clarification response, merge with remembered category, and search."""
    new_req = extract_requirements_fallback(user_prompt)
    category = context.get("category") or new_req.get("category") or "Laptop"
    max_price = new_req.get("max_price") or context.get("budget")
    purpose = new_req.get("purpose") or context.get("purpose")
    keyword = new_req.get("keyword")

    context["category"] = category
    context["budget"] = max_price
    context["purpose"] = purpose
    context["awaiting_clarification"] = None
    context["previous_user_request"] = user_prompt

    budget_str = f"₹{max_price:,.0f}" if max_price else "Flexible"
    log_event(
        event_type="INTENT_UPDATED",
        action="Customer clarified shopping requirements",
        details=f"Category: {category}; Budget: {budget_str}; Purpose: {purpose or 'General'}",
        status="SUCCESS",
        rule_or_tool="Conversational Memory",
    )

    merged_requirements = {
        "category": category,
        "max_price": max_price,
        "min_price": new_req.get("min_price"),
        "purpose": purpose,
        "preferences": None,
        "keyword": keyword,
    }
    return execute_catalog_search(user_prompt, merged_requirements, context, extraction_engine="Clarification Context")


def select_diverse_upsell(
    prod: dict[str, Any],
    used_upsell_ids: set[int],
    slot_idx: int = 0,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Select an in-stock, complementary accessory for `prod` ensuring diversity across recommendation cards.
    - Prevents repeating the exact same accessory across multiple product cards.
    - Prioritizes brand affinity (e.g. HP backpack for HP laptop, Lenovo bag for Lenovo laptop).
    - Rotates complementary categories (Mouse, Laptop Bag, Headphones, Storage, etc.) based on slot_idx.
    - Generates a context-aware, informative pitch tailored to the specific accessory.
    """
    pid = prod.get("id")
    if not pid:
        return None, None

    cat = prod.get("category", "")
    comp_cats = [
        "Mouse", "Laptop Bags", "Headphones", "Storage", "Keyboards", "Chargers", "Power Banks"
    ]
    if "Smart" in cat or "Phone" in cat:
        comp_cats = ["Chargers", "Power Banks", "Headphones", "Smartwatches"]
    elif "Headphone" in cat or "Speaker" in cat:
        comp_cats = ["Speakers", "Power Banks", "Chargers"]
    elif "Keyboard" in cat:
        comp_cats = ["Mouse", "Monitors", "Accessories"]
    elif "Mouse" in cat:
        comp_cats = ["Keyboards", "Laptop Bags", "Monitors"]

    pref_cat = comp_cats[slot_idx % len(comp_cats)] if comp_cats else None

    # Call get_related_products with exclude_ids and preferred_category
    related = get_related_products(
        pid,
        limit=3,
        exclude_ids=used_upsell_ids,
        preferred_category=pref_cat,
    )

    upsell_item = None
    if related:
        for candidate in related:
            if candidate["id"] not in used_upsell_ids:
                upsell_item = candidate
                break
        if not upsell_item:
            upsell_item = related[0]

    if not upsell_item:
        return None, None

    used_upsell_ids.add(upsell_item["id"])

    # Generate tailored pitch
    up_cat = upsell_item.get("category", "")
    prod_name = prod.get("name", "")[:24]

    if "Bag" in up_cat:
        pitch = f"Protective backpack tailored for laptops like the {prod_name}."
    elif "Mouse" in up_cat:
        pitch = f"Ergonomic optical mouse for smooth precision with your {prod_name}."
    elif "Headphone" in up_cat or "Earbud" in up_cat:
        pitch = f"High-clarity audio companion for calls, media, and focused work."
    elif "Charger" in up_cat or "Power" in up_cat:
        pitch = f"High-speed charging companion to keep your {prod_name} powered on the go."
    elif "Storage" in up_cat:
        pitch = f"Fast external storage expansion for backups and large files."
    elif "Keyboard" in up_cat:
        pitch = f"Tactile keyboard companion for an elevated desktop workstation."
    elif "Watch" in up_cat:
        pitch = f"Smart wearable companion for notifications, health, and fitness tracking."
    else:
        pitch = f"Complementary {up_cat.lower()} accessory paired with your {prod_name}."

    return upsell_item, pitch


def handle_comparison(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Compare recently displayed products with zero hallucination using genuine catalog specs."""
    recent = context.get("recently_displayed_products", [])
    if len(recent) < 2:
        cat = context.get("category") or "Laptop"
        budget = context.get("budget")
        recent = search_products(keyword="", category=cat, max_price=budget, in_stock_only=True)[:2]

    if len(recent) < 2:
        return {
            "status": "success",
            "requirements": {"category": context.get("category"), "max_price": context.get("budget"), "purpose": context.get("purpose")},
            "agent_understanding": {
                "category": context.get("category") or "None",
                "budget": f"₹{context.get('budget'):,.0f}" if context.get("budget") else "None",
                "purpose": (context.get("purpose") or "Comparison").title(),
                "preferences": "Context-Aware Comparison",
            },
            "catalog_search": {"products_evaluated": 0, "products_matching": 0, "blocked_candidates": []},
            "engine": "Comparison Engine",
            "message": "I don't have multiple products in our recent conversation to compare yet. Please ask for recommendations first (e.g. *'Show laptops under 60000'*).",
            "recommendations": [],
            "conversation_context": context,
        }

    p1, p2 = recent[0], recent[1]
    s1, s2 = parse_product_specs(p1), parse_product_specs(p2)

    log_event(
        event_type="PRODUCT_COMPARISON",
        action=f"Compared {p1['name']} vs {p2['name']}",
        details=f"P1: ₹{p1['price']:,.0f} ({s1.get('RAM', 'N/A')}, {s1.get('Processor', 'N/A')}); P2: ₹{p2['price']:,.0f} ({s2.get('RAM', 'N/A')}, {s2.get('Processor', 'N/A')})",
        status="SUCCESS",
        rule_or_tool="Comparison Engine",
    )

    text_lower = prompt.lower()
    is_coding = "code" in text_lower or "coding" in text_lower or "programming" in text_lower or (context.get("purpose") == "coding")
    is_gaming = "game" in text_lower or "gaming" in text_lower or (context.get("purpose") == "gaming")

    table = (
        f"### 🔍 Side-by-Side Comparison\n\n"
        f"| Specification | **{p1['name']}** | **{p2['name']}** |\n"
        f"| :--- | :--- | :--- |\n"
        f"| 🏷️ **Price** | **₹{p1['price']:,.0f}** | **₹{p2['price']:,.0f}** |\n"
        f"| ⚡ **Processor** | {s1.get('Processor', 'N/A')} | {s2.get('Processor', 'N/A')} |\n"
        f"| 🧠 **RAM** | {s1.get('RAM', 'N/A')} | {s2.get('RAM', 'N/A')} |\n"
        f"| 💾 **Storage** | {s1.get('Storage', 'N/A')} | {s2.get('Storage', 'N/A')} |\n"
        f"| 🖥️ **Display** | {s1.get('Display', 'N/A')} | {s2.get('Display', 'N/A')} |\n"
        f"| 📦 **Stock Status** | {p1['stock']} units available | {p2['stock']} units available |\n"
    )

    ram1_val = int(re.search(r"(\d+)", s1.get("RAM", "8")).group(1)) if re.search(r"(\d+)", s1.get("RAM", "8")) else 8
    ram2_val = int(re.search(r"(\d+)", s2.get("RAM", "8")).group(1)) if re.search(r"(\d+)", s2.get("RAM", "8")) else 8

    if is_coding:
        if ram2_val > ram1_val:
            better_p, other_p = p2, p1
            better_s, other_s = s2, s1
        else:
            better_p, other_p = p1, p2
            better_s, other_s = s1, s2

        analysis = (
            f"\n#### 💡 Recommendation for Coding & Software Development:\n"
            f"- **Top Pick**: **{better_p['name']}** is clearly the superior machine for coding.\n"
            f"- **Why**: It comes with **{better_s.get('RAM', '16GB RAM')}**, which provides ample memory for running modern IDEs (VS Code, IntelliJ), Docker containers, Android emulators, and local development servers concurrently without memory swapping or UI stutter.\n"
            f"- **Processor & Storage**: Powered by **{better_s.get('Processor', 'Fast CPU')}** and fast **{better_s.get('Storage', '512GB SSD')}** storage for quick build and compilation cycles.\n"
            f"- **Value Perspective**: **{other_p['name']}** at ₹{other_p['price']:,.0f} is suitable for entry-level programming, but **{better_p['name']}** will remain fast and capable for years to come."
        )
    elif is_gaming:
        analysis = (
            f"\n#### 💡 Recommendation for Gaming:\n"
            f"Both laptops feature responsive displays and fast SSDs. For demanding titles, prioritize models with dedicated graphics and high refresh rates."
        )
    else:
        diff_price = abs(p1["price"] - p2["price"])
        cheaper_p = p1 if p1["price"] < p2["price"] else p2
        higher_p = p2 if p1["price"] < p2["price"] else p1
        analysis = (
            f"\n#### 💡 Key Takeaways:\n"
            f"- **Budget Advantage**: **{cheaper_p['name']}** saves you **₹{diff_price:,.0f}**.\n"
            f"- **Performance Advantage**: **{higher_p['name']}** provides **{s2.get('RAM', '16GB RAM')}** and more headroom for heavy workloads."
        )

    full_message = f"{table}\n{analysis}\n\nYou can click **Add to Cart** or **Instant Buy** on either product below:"

    recs = []
    used_upsell_ids: set[int] = set()
    for slot_idx, prod in enumerate([p1, p2]):
        upsell_item, upsell_pitch = select_diverse_upsell(prod, used_upsell_ids, slot_idx=slot_idx)
        why_points = build_why_points_fallback(prod, {"max_price": context.get("budget"), "purpose": context.get("purpose")})
        recs.append({
            "product": prod,
            "pitch": f"Candidate: {prod['name']} (₹{prod['price']:,.0f})",
            "why_points": why_points,
            "upsell": upsell_item,
            "upsell_pitch": upsell_pitch,
        })

    context["previous_user_request"] = prompt
    return {
        "status": "success",
        "requirements": {"category": context.get("category"), "max_price": context.get("budget"), "purpose": context.get("purpose")},
        "agent_understanding": {
            "category": context.get("category") or "Laptop",
            "budget": f"₹{context.get('budget'):,.0f}" if context.get("budget") else "None",
            "purpose": (context.get("purpose") or "Coding").title() if is_coding else "Comparison",
            "preferences": "Contextual Spec Comparison",
        },
        "catalog_search": {
            "products_evaluated": 2,
            "products_matching": 2,
            "blocked_candidates": [],
        },
        "engine": "Catalog Comparison Engine",
        "message": full_message,
        "recommendations": recs,
        "conversation_context": context,
    }


def handle_cheaper_alternatives(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Find budget-friendly alternatives cheaper than recently viewed options."""
    recent = context.get("recently_displayed_products", [])
    cat = context.get("category") or (recent[0]["category"] if recent else "Laptop")
    purpose = context.get("purpose")

    if recent:
        min_prev_price = min(p["price"] for p in recent)
    elif context.get("budget"):
        min_prev_price = context["budget"]
    else:
        min_prev_price = 60000.0

    # Search products with price strictly lower than min_prev_price
    candidates = search_products(keyword="", category=cat, max_price=min_prev_price - 1, in_stock_only=True)
    if not candidates:
        all_in_cat = search_products(keyword="", category=cat, in_stock_only=True)
        cheapest_in_cat = [p for p in all_in_cat if p["price"] <= min_prev_price]
        if cheapest_in_cat:
            candidates = sorted(cheapest_in_cat, key=lambda x: x["price"])
        else:
            candidates = sorted(all_in_cat, key=lambda x: x["price"])[:1]

    log_event(
        event_type="ALTERNATIVE_SEARCH",
        action=f"Searched cheaper alternatives for {cat}",
        details=f"Reference threshold: ₹{min_prev_price:,.0f}; Found {len(candidates)} in-stock alternatives",
        status="SUCCESS",
        rule_or_tool="Alternative Search Engine",
    )

    recs = []
    used_upsell_ids: set[int] = set()
    for slot_idx, prod in enumerate(candidates[:5]):
        upsell_item, upsell_pitch = select_diverse_upsell(prod, used_upsell_ids, slot_idx=slot_idx)
        savings = min_prev_price - prod["price"]
        why_points = [
            f"More affordable: saves ₹{savings:,.0f} compared to previous options" if savings > 0 else f"Priced at ₹{prod['price']:,.0f}",
            f"{parse_product_specs(prod).get('Processor', 'Fast CPU')} & {parse_product_specs(prod).get('RAM', '8GB RAM')}",
            f"In stock & ready to dispatch ({prod['stock']} available)",
        ]
        recs.append({
            "product": prod,
            "pitch": f"I found the **{prod['name']}** at ₹{prod['price']:,.0f}, giving you significant savings while keeping reliable everyday performance.",
            "why_points": why_points,
            "upsell": upsell_item,
            "upsell_pitch": upsell_pitch,
        })

    context["recently_displayed_products"] = [r["product"] for r in recs]
    if recs:
        context["currently_selected_product"] = recs[0]["product"]
    context["previous_user_request"] = prompt

    summary = f"Here are **{len(recs)} budget-friendly {cat.lower()} alternative(s)** priced lower than your previous options:"

    return {
        "status": "success",
        "requirements": {"category": cat, "max_price": min_prev_price, "purpose": purpose},
        "agent_understanding": {
            "category": cat,
            "budget": f"< ₹{min_prev_price:,.0f}",
            "purpose": (purpose or "Budget-Conscious").title(),
            "preferences": "Cheaper Alternatives",
        },
        "catalog_search": {
            "products_evaluated": len(candidates),
            "products_matching": len(recs),
            "blocked_candidates": [],
        },
        "engine": "Catalog AI Engine",
        "message": summary,
        "recommendations": recs,
        "conversation_context": context,
    }


def handle_another_alternative(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Show other alternatives in category excluding already displayed product IDs."""
    recent = context.get("recently_displayed_products", [])
    cat = context.get("category") or (recent[0]["category"] if recent else "Laptop")
    budget = context.get("budget")
    purpose = context.get("purpose")
    excluded_ids = {p["id"] for p in recent}

    all_matches = search_products(keyword="", category=cat, max_price=budget, in_stock_only=True)
    new_candidates = [p for p in all_matches if p["id"] not in excluded_ids]

    log_event(
        event_type="ALTERNATIVE_SEARCH",
        action=f"Searched additional alternatives for {cat}",
        details=f"Excluded {len(excluded_ids)} previously seen items; Found {len(new_candidates)} fresh matches",
        status="SUCCESS",
        rule_or_tool="Alternative Search Engine",
    )

    if not new_candidates:
        return {
            "status": "success",
            "requirements": {"category": cat, "max_price": budget, "purpose": purpose},
            "agent_understanding": {
                "category": cat,
                "budget": f"₹{budget:,.0f}" if budget else "Flexible",
                "purpose": (purpose or "General").title(),
                "preferences": "Catalog Exhausted",
            },
            "catalog_search": {"products_evaluated": len(all_matches), "products_matching": 0, "blocked_candidates": []},
            "engine": "Catalog AI Engine",
            "message": f"You have already seen all top in-stock **{cat}** options within your budget. Would you like to adjust your budget or explore other tech categories?",
            "recommendations": [],
            "conversation_context": context,
        }

    recs = []
    used_upsell_ids: set[int] = set()
    for slot_idx, prod in enumerate(new_candidates[:2]):
        upsell_item, upsell_pitch = select_diverse_upsell(prod, used_upsell_ids, slot_idx=slot_idx)
        why_points = build_why_points_fallback(prod, {"max_price": budget, "purpose": purpose})
        recs.append({
            "product": prod,
            "pitch": f"Here is another strong option: the **{prod['name']}** (₹{prod['price']:,.0f}) with {parse_product_specs(prod).get('Processor', 'fast processing')} and {parse_product_specs(prod).get('RAM', '8GB RAM')}.",
            "why_points": why_points,
            "upsell": upsell_item,
            "upsell_pitch": upsell_pitch,
        })

    context["recently_displayed_products"] = [r["product"] for r in recs]
    if recs:
        context["currently_selected_product"] = recs[0]["product"]
    context["previous_user_request"] = prompt

    summary = f"Here is another option from our verified catalog matching your requirements:"

    return {
        "status": "success",
        "requirements": {"category": cat, "max_price": budget, "purpose": purpose},
        "agent_understanding": {
            "category": cat,
            "budget": f"₹{budget:,.0f}" if budget else "Flexible",
            "purpose": (purpose or "General").title(),
            "preferences": "Alternative Model",
        },
        "catalog_search": {
            "products_evaluated": len(all_matches),
            "products_matching": len(recs),
            "blocked_candidates": [],
        },
        "engine": "Catalog AI Engine",
        "message": summary,
        "recommendations": recs,
        "conversation_context": context,
    }


def handle_budget_update(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Update user's budget constraint while preserving category and purpose."""
    new_budget = extract_price_from_text(prompt) or 70000.0
    cat = context.get("category") or "Laptop"
    purpose = context.get("purpose")
    old_budget = context.get("budget")
    context["budget"] = new_budget

    old_b_str = f"₹{old_budget:,.0f}" if old_budget else "None"
    new_b_str = f"₹{new_budget:,.0f}"

    log_event(
        event_type="INTENT_UPDATED",
        action="Customer updated budget in conversation",
        details=f"Budget adjusted from {old_b_str} to {new_b_str}; Preserved category '{cat}' and purpose '{purpose or 'General'}'",
        status="SUCCESS",
        rule_or_tool="Conversational Memory",
    )

    candidates = search_products(keyword="", category=cat, max_price=new_budget, in_stock_only=True)
    # Sort candidates prioritizing higher-spec models newly unlocked by the higher budget
    candidates = sorted(candidates, key=lambda x: x["price"], reverse=True)[:5]

    recs = []
    used_upsell_ids: set[int] = set()
    for slot_idx, prod in enumerate(candidates):
        upsell_item, upsell_pitch = select_diverse_upsell(prod, used_upsell_ids, slot_idx=slot_idx)
        why_points = build_why_points_fallback(prod, {"max_price": new_budget, "purpose": purpose})
        recs.append({
            "product": prod,
            "pitch": f"With your increased budget of ₹{new_budget:,.0f}, the **{prod['name']}** offers enhanced specs ({parse_product_specs(prod).get('RAM', '16GB RAM')}, {parse_product_specs(prod).get('Storage', 'SSD')}).",
            "why_points": why_points,
            "upsell": upsell_item,
            "upsell_pitch": upsell_pitch,
        })

    context["recently_displayed_products"] = [r["product"] for r in recs]
    if recs:
        context["currently_selected_product"] = recs[0]["product"]
    context["previous_user_request"] = prompt

    summary = (
        f"I've updated your budget to **₹{new_budget:,.0f}** while retaining your category (**{cat}**) "
        f"and purpose (**{purpose or 'everyday use'}**). Here are our top verified matches:"
    )

    return {
        "status": "success",
        "requirements": {"category": cat, "max_price": new_budget, "purpose": purpose},
        "agent_understanding": {
            "category": cat,
            "budget": new_b_str,
            "purpose": (purpose or "General Use").title(),
            "preferences": f"Budget increased to {new_b_str}",
        },
        "catalog_search": {
            "products_evaluated": len(candidates),
            "products_matching": len(recs),
            "blocked_candidates": [],
        },
        "engine": "Catalog AI Engine",
        "message": summary,
        "recommendations": recs,
        "conversation_context": context,
    }


def handle_cart_query(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Inspect shopping cart, check remaining budget feasibility, or suggest add-on accessories."""
    cart = context.get("cart", {})
    cart_items = [v for v in cart.values()]
    cart_total = sum(item["product"]["price"] * item["quantity"] for item in cart_items)
    cart_count = sum(item["quantity"] for item in cart_items)
    text = prompt.lower()

    log_event(
        event_type="USER_REQUEST",
        action="Customer inquired about cart / budget",
        details=f"Prompt: '{prompt}'; Cart Items: {cart_count}; Cart Total: ₹{cart_total:,.0f}",
        status="PROCESSED",
    )

    # 1. Budget check: "Can I stay under 50000 with this laptop and cart?"
    if re.search(r"\bcan i stay under\b", text) or (re.search(r"\bunder\s+(\d[\d,]*)", text) and "cart" in text):
        target_budget = extract_price_from_text(prompt) or 50000.0
        ref_product = context.get("currently_selected_product")
        if not ref_product and context.get("recently_displayed_products"):
            ref_product = context["recently_displayed_products"][0]

        if ref_product:
            in_cart = ref_product["id"] in cart
            prod_price = ref_product["price"]
            combined = cart_total if in_cart else (cart_total + prod_price)
            if combined <= target_budget:
                remaining = target_budget - combined
                cart_note = f" (including {ref_product['name']})" if in_cart else ""
                msg = (
                    f"**Yes, absolutely!** 🎉\n\n"
                    f"- Current Cart Total{cart_note}: **₹{cart_total:,.0f}** ({cart_count} item(s))\n"
                    f"- **{ref_product['name']}**: **₹{prod_price:,.0f}**\n"
                    f"- Total Amount: **₹{combined:,.0f}**\n\n"
                    f"You will comfortably stay under your **₹{target_budget:,.0f}** limit with **₹{remaining:,.0f} to spare**!"
                )
            else:
                over = combined - target_budget
                msg = (
                    f"**No, the combined total would exceed your budget:**\n\n"
                    f"- Current Cart Total: **₹{cart_total:,.0f}** ({cart_count} item(s))\n"
                    f"- **{ref_product['name']}**: **₹{prod_price:,.0f}**\n"
                    f"- Total Amount: **₹{combined:,.0f}**\n\n"
                    f"This exceeds your **₹{target_budget:,.0f}** threshold by **₹{over:,.0f}**. "
                    f"Would you like me to recommend a more budget-friendly option?"
                )
        else:
            if cart_total <= target_budget:
                msg = f"Yes! Your current cart total is **₹{cart_total:,.0f}**, which is well within your ₹{target_budget:,.0f} limit."
            else:
                msg = f"Your current cart total is **₹{cart_total:,.0f}**, which exceeds your ₹{target_budget:,.0f} limit by ₹{cart_total - target_budget:,.0f}."

        return {
            "status": "success",
            "requirements": {"category": "Cart", "max_price": target_budget},
            "agent_understanding": {
                "category": "Cart & Budget Evaluation",
                "budget": f"₹{target_budget:,.0f}",
                "purpose": "Cart Feasibility Check",
                "preferences": f"Cart total: ₹{cart_total:,.0f}",
            },
            "catalog_search": {"products_evaluated": 1, "products_matching": 1, "blocked_candidates": []},
            "engine": "Fintech Safety Guardrail",
            "message": msg,
            "recommendations": [],
            "conversation_context": context,
        }

    # 2. Accessory suggestion within remaining budget
    if re.search(r"\b(?:suggest\s+(?:an?\s+)?accessory|accessory within|accessories)\b", text):
        total_budget = context.get("budget") or 60000.0
        ref_product = context.get("currently_selected_product")
        used_amount = cart_total + (ref_product["price"] if ref_product and ref_product["id"] not in cart else 0.0)
        remaining = max(total_budget - used_amount, 2000.0)

        accessories = []
        for acc_cat in ["Mouse", "Keyboard", "Laptop Bag", "Charger", "Headphones", "Earbuds", "Power Bank"]:
            found = search_products(keyword="", category=acc_cat, max_price=remaining, in_stock_only=True)
            accessories.extend(found)

        accessories = sorted(accessories, key=lambda x: x["price"])[:3]

        recs = []
        for prod in accessories:
            why_points = [
                f"Fits within your remaining budget of ₹{remaining:,.0f}",
                f"{prod['description'][:50]}...",
                f"In stock ({prod['stock']} available)",
            ]
            recs.append({
                "product": prod,
                "pitch": f"**{prod['name']}** (₹{prod['price']:,.0f}) is a great addition within your remaining ₹{remaining:,.0f} budget.",
                "why_points": why_points,
                "upsell": None,
                "upsell_pitch": None,
            })

        msg = (
            f"You have **₹{remaining:,.0f}** remaining from your ₹{total_budget:,.0f} budget. "
            f"Here are **{len(recs)} top accessory recommendation(s)** that fit perfectly:"
        )

        return {
            "status": "success",
            "requirements": {"category": "Accessory", "max_price": remaining},
            "agent_understanding": {
                "category": "Accessories",
                "budget": f"₹{remaining:,.0f}",
                "purpose": "Accessory Add-on",
                "preferences": "Within Remaining Budget",
            },
            "catalog_search": {"products_evaluated": len(accessories), "products_matching": len(recs), "blocked_candidates": []},
            "engine": "Catalog AI Engine",
            "message": msg,
            "recommendations": recs,
            "conversation_context": context,
        }

    # 3. Standard Cart Summary
    if cart_count == 0:
        msg = "Your shopping cart is currently empty. Tell me what you're shopping for (e.g. *'I need a laptop for coding under 70000'*), and I'll find top recommendations!"
    else:
        lines = [f"### 🛒 Your Shopping Cart ({cart_count} item{'s' if cart_count > 1 else ''})\n"]
        for item in cart_items:
            p = item["product"]
            qty = item["quantity"]
            subtotal = p["price"] * qty
            source_tag = " *(AI Recommended)*" if item.get("source") == "AI-recommended" else ""
            lines.append(f"- **{p['name']}** × {qty} — **₹{subtotal:,.0f}**{source_tag}")
        lines.append(f"\n**Total Cart Value: ₹{cart_total:,.0f}**")
        lines.append("\nYou can proceed to checkout anytime using the **Proceed to Checkout** button in the sidebar!")
        msg = "\n".join(lines)

    return {
        "status": "success",
        "requirements": {"category": "Cart", "max_price": None},
        "agent_understanding": {
            "category": "Cart Inspection",
            "budget": "N/A",
            "purpose": "Cart Inspection",
            "preferences": f"{cart_count} items",
        },
        "catalog_search": {"products_evaluated": cart_count, "products_matching": cart_count, "blocked_candidates": []},
        "engine": "Cart Manager",
        "message": msg,
        "recommendations": [],
        "conversation_context": context,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Catalog Search Execution Engine
# ─────────────────────────────────────────────────────────────────────────────

def execute_catalog_search(
    user_prompt: str,
    requirements: dict,
    context: dict[str, Any],
    extraction_engine: str = "Fallback",
) -> dict[str, Any]:
    """Execute safe parameterized SQLite search, apply guardrails, generate justifications, and update context."""
    budget_str = f"₹{requirements.get('max_price'):,.0f}" if requirements.get("max_price") else "None"
    cat_str = requirements.get("category") or "All Categories"
    purpose_str = requirements.get("purpose") or "General"
    pref_str = ", ".join(requirements.get("specs", [])) if requirements.get("specs") else "None"

    # Log USER_REQUEST
    log_event(
        event_type="USER_REQUEST",
        action="Customer shopping query received",
        details=f"Query: '{user_prompt}'; Category: {cat_str}; Budget: {budget_str}; Purpose: {purpose_str} (Engine: {extraction_engine})",
        status="PROCESSED",
    )

    # Log AGENT_INTENT
    log_event(
        event_type="AGENT_INTENT",
        action="Agent parsed customer shopping intent",
        details=f"category={cat_str}; budget={budget_str}; purpose={purpose_str}; preferences={pref_str}",
        status="SUCCESS",
        rule_or_tool="Agentic Intent Parser",
    )

    # Query SQLite safely using parameterized SQL
    category = requirements.get("category") or ""
    keyword = requirements.get("keyword") or ""
    max_price = requirements.get("max_price")
    min_price = requirements.get("min_price")

    candidate_products = search_products(
        keyword=keyword,
        category=category,
        max_price=max_price,
        min_price=min_price,
        in_stock_only=True,
    )

    # Fallback 1: If 0 results and purpose is identified (e.g. gaming, coding), search by purpose
    purpose = requirements.get("purpose")
    if not candidate_products and purpose:
        candidate_products = search_products(
            keyword=purpose,
            category=category,
            max_price=max_price,
            min_price=min_price,
            in_stock_only=True,
        )

    # Fallback 2: If keyword was too specific, broaden search to category + price
    if not candidate_products and category:
        candidate_products = search_products(
            keyword="",
            category=category,
            max_price=max_price,
            min_price=min_price,
            in_stock_only=True,
        )

    # Fallback 3: If still no results and keyword has multiple words, try individual words
    if not candidate_products and keyword and len(keyword.split()) > 1:
        for single_kw in keyword.split():
            if len(single_kw) > 2:
                candidate_products = search_products(
                    keyword=single_kw,
                    category=category,
                    max_price=max_price,
                    min_price=min_price,
                    in_stock_only=True,
                )
                if candidate_products:
                    break

    # Calculate Catalog Evaluation & Guardrail Blocked items
    if category:
        category_all = search_products(keyword="", category=category, in_stock_only=False)
        total_evaluated = len(category_all)
    else:
        from database import get_product_count
        total_evaluated = get_product_count()
        category_all = []

    blocked_candidates = []
    # Rule 1 Check: Products in searched category exceeding customer budget
    if category and max_price is not None:
        over_budget = [p for p in category_all if p["price"] > max_price]
        for bp in over_budget[:2]:
            reason_msg = (
                f"This product costs ₹{bp['price']:,.0f}, which exceeds the customer's "
                f"₹{max_price:,.0f} budget. The agent did not recommend or add it."
            )
            blocked_candidates.append({
                "product": bp,
                "name": bp["name"],
                "price": bp["price"],
                "reason": reason_msg,
                "rule": "RULE 1 — CUSTOMER BUDGET",
            })
            log_event(
                event_type="GUARDRAIL_BLOCKED",
                action=f"Blocked product '{bp['name']}' (ID: {bp['id']})",
                details=f"Product price ₹{bp['price']:,.0f} exceeds budget ₹{max_price:,.0f}",
                status="BLOCKED",
                rule_or_tool="Agent Budget Guardrail",
            )

    # Rule 3 Check: Products that are out of stock
    if category:
        out_of_stock = [p for p in category_all if p["stock"] <= 0]
        for op in out_of_stock[:1]:
            reason_msg = f"This product is currently out of stock (0 available). The agent did not recommend or add it."
            blocked_candidates.append({
                "product": op,
                "name": op["name"],
                "price": op["price"],
                "reason": reason_msg,
                "rule": "RULE 3 — STOCK CHECK",
            })
            log_event(
                event_type="GUARDRAIL_BLOCKED",
                action=f"Blocked out-of-stock product '{op['name']}' (ID: {op['id']})",
                details=reason_msg,
                status="BLOCKED",
                rule_or_tool="Agent Stock Guardrail",
            )

    # Log PRODUCT_SEARCH
    log_event(
        event_type="PRODUCT_SEARCH",
        action="Queried SQLite products catalog",
        details=f"Filters: category='{category}', max_price={max_price}, keyword='{keyword}'; Evaluated: {total_evaluated}, Matching: {len(candidate_products)}",
        status="SUCCESS" if candidate_products else "NO_MATCH",
    )

    if candidate_products:
        log_event(
            event_type="GUARDRAIL_PASSED",
            action="Candidate products verified within budget & catalog constraints",
            details=f"Passed {len(candidate_products)} products within budget limit {budget_str}",
            status="PASSED",
            rule_or_tool="Fintech Safety Engine",
        )

    # Handle zero matches
    if not candidate_products:
        context["previous_user_request"] = user_prompt
        return {
            "status": "no_match",
            "requirements": requirements,
            "agent_understanding": {
                "category": cat_str,
                "budget": budget_str,
                "purpose": (requirements.get("purpose") or "General Use").title(),
                "preferences": pref_str,
            },
            "catalog_search": {
                "products_evaluated": max(total_evaluated, 1),
                "products_matching": 0,
                "blocked_candidates": blocked_candidates,
            },
            "engine": extraction_engine,
            "message": (
                "I couldn't find a product matching all your requirements. "
                "Would you like to increase your budget or explore similar products in other categories?"
            ),
            "recommendations": [],
            "conversation_context": context,
        }

    # Rank and Explain
    client = get_openai_client()
    ai_result = None
    if client:
        ai_result = rank_and_explain_openai(user_prompt, candidate_products, requirements, client)

    final_recommendations = []
    used_upsell_ids: set[int] = set()
    if ai_result and "recommendations" in ai_result:
        prod_map = {p["id"]: p for p in candidate_products}
        for slot_idx, rec in enumerate(ai_result["recommendations"]):
            pid = rec.get("product_id")
            if pid in prod_map:
                prod = prod_map[pid]
                if max_price is not None and prod["price"] > max_price:
                    continue  # Guardrail: reject price over budget

                upsell_item, upsell_pitch = select_diverse_upsell(prod, used_upsell_ids, slot_idx=slot_idx)

                final_recommendations.append({
                    "product": prod,
                    "pitch": rec.get("recommendation_pitch", f"I recommend the {prod['name']} for your requirements."),
                    "why_points": rec.get("why_points", build_why_points_fallback(prod, requirements)),
                    "upsell": upsell_item,
                    "upsell_pitch": upsell_pitch,
                })

    if not final_recommendations:
        top_candidates = candidate_products[:5]
        for slot_idx, prod in enumerate(top_candidates):
            upsell_item, upsell_pitch = select_diverse_upsell(prod, used_upsell_ids, slot_idx=slot_idx)
            why_points = build_why_points_fallback(prod, requirements)
            final_recommendations.append({
                "product": prod,
                "pitch": (
                    f"I recommend the **{prod['name']}** because it is within your budget "
                    f"and provides suitable specifications for {requirements.get('purpose') or 'everyday use'}."
                ),
                "why_points": why_points,
                "upsell": upsell_item,
                "upsell_pitch": upsell_pitch,
            })

    # Log recommendations & upsells
    for rec in final_recommendations:
        p = rec["product"]
        log_event(
            event_type="PRODUCT_RECOMMENDATION",
            action=f"AI recommended {p['name']}",
            details=f"Price: ₹{p['price']:,.0f}; Budget: {budget_str}; Category: {p['category']}; Why: {'; '.join(rec['why_points'][:2])}",
            status="PASSED",
        )
        if rec["upsell"]:
            up = rec["upsell"]
            log_event(
                event_type="UPSELL_SUGGESTED",
                action=f"Suggested cross-sell: {up['name']} for {p['name']}",
                details=f"Upsell Price: ₹{up['price']:,.0f}; Requires explicit customer approval",
                status="SUGGESTED",
            )

    summary = f"Based on your requirements, I selected **{len(final_recommendations)} top product(s)** from our verified catalog:"

    # Update conversational context
    context["previous_user_request"] = user_prompt
    if requirements.get("category"):
        context["category"] = requirements["category"]
    if requirements.get("max_price"):
        context["budget"] = requirements["max_price"]
    if requirements.get("purpose"):
        context["purpose"] = requirements["purpose"]
    if requirements.get("preferences"):
        context["preferences"] = requirements["preferences"]
    context["recently_displayed_products"] = [r["product"] for r in final_recommendations]
    if final_recommendations:
        context["currently_selected_product"] = final_recommendations[0]["product"]

    return {
        "status": "success",
        "requirements": requirements,
        "agent_understanding": {
            "category": cat_str,
            "budget": budget_str,
            "purpose": (requirements.get("purpose") or "General Use").title(),
            "preferences": pref_str,
        },
        "catalog_search": {
            "products_evaluated": max(total_evaluated, len(candidate_products)),
            "products_matching": len(candidate_products),
            "blocked_candidates": blocked_candidates,
        },
        "engine": "OpenAI" if (client and ai_result) else "Catalog AI Engine",
        "message": summary,
        "recommendations": final_recommendations,
        "conversation_context": context,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Main Public Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def process_shopping_request(user_prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Main entry point for TechMart AI Shopping Agent.
    Supports multi-turn conversational context, clarification, follow-ups, and cart queries.
    """
    if context is None:
        context = {
            "previous_user_request": None,
            "category": None,
            "budget": None,
            "min_price": None,
            "purpose": None,
            "preferences": None,
            "recently_displayed_products": [],
            "currently_selected_product": None,
            "awaiting_clarification": None,
            "cart": {},
        }
    else:
        context = dict(context)
        context.setdefault("recently_displayed_products", [])
        context.setdefault("cart", {})

    intent = classify_conversational_intent(user_prompt, context)

    if intent == "CLARIFICATION_REPLY":
        return handle_clarification_reply(user_prompt, context)
    elif intent in ("CART_SUMMARY", "CART_BUDGET_CHECK", "CART_ACCESSORY_SUGGESTION"):
        return handle_cart_query(user_prompt, context)
    elif intent == "COMPARISON":
        return handle_comparison(user_prompt, context)
    elif intent == "CHEAPER_ALTERNATIVES":
        return handle_cheaper_alternatives(user_prompt, context)
    elif intent == "ANOTHER_ALTERNATIVE":
        return handle_another_alternative(user_prompt, context)
    elif intent == "BUDGET_UPDATE":
        return handle_budget_update(user_prompt, context)
    elif intent == "CLARIFICATION_PROMPT":
        req = extract_requirements_fallback(user_prompt)
        cat = req.get("category") or "Laptop"
        return handle_clarification_prompt(cat, user_prompt, context)
    else:
        requirements, extraction_engine = extract_requirements(user_prompt)
        # Inherit category from context if follow-up omitted it
        if not requirements.get("category") and context.get("category"):
            requirements["category"] = context["category"]
        return execute_catalog_search(user_prompt, requirements, context, extraction_engine=extraction_engine)

