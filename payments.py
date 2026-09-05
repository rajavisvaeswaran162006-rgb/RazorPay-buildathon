"""
payments.py — TechMart AI Shopping Agent
=========================================
Fintech payment module supporting Razorpay Test Mode and zero-crash simulation mode.

Features:
  - Razorpay Python SDK integration (client.order.create)
  - Automatic conversion to paise (₹1 = 100 paise)
  - Seamless fallback to Test Simulation Mode when credentials are not supplied
  - Cryptographic signature verification support
"""

import os
import time
import uuid
import logging
from typing import Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()


def is_live_key_configured() -> bool:
    """Return True if real Razorpay test keys are present in .env."""
    key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    return bool(key_id and key_secret and not key_id.startswith("your_") and not key_secret.startswith("your_"))


def get_razorpay_client():
    """Create Razorpay SDK client if credentials are configured."""
    if not is_live_key_configured():
        return None
    try:
        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        client.set_app_details({"title": "TechMart AI Shopping Agent", "version": "1.0.0"})
        return client
    except Exception as e:
        logger.warning(f"Failed to initialize Razorpay client: {e}")
        return None


def create_razorpay_order(
    amount_inr: float,
    receipt_id: str,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Create a Razorpay order in INR.

    Parameters
    ----------
    amount_inr : Order total in rupees
    receipt_id : Internal receipt tracking identifier
    notes      : Additional metadata attached to the order

    Returns
    -------
    dict containing order details: 'id', 'amount', 'currency', 'receipt', 'status', 'mode'
    """
    amount_paise = int(round(amount_inr * 100))
    payload_notes = notes or {"agent": "TechMart AI Shopping Agent"}

    client = get_razorpay_client()
    if client:
        try:
            data = {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt_id,
                "notes": payload_notes,
            }
            order = client.order.create(data=data)
            order["mode"] = "live_test"
            logger.info(f"Created live Razorpay order: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {e}. Falling back to simulation mode.")

    # ── Simulation Mode (Guaranteed zero-crash for demo) ────────────────
    mock_order_id = f"order_test_{uuid.uuid4().hex[:14]}"
    mock_order = {
        "id": mock_order_id,
        "entity": "order",
        "amount": amount_paise,
        "amount_paid": 0,
        "amount_due": amount_paise,
        "currency": "INR",
        "receipt": receipt_id,
        "status": "created",
        "attempts": 0,
        "notes": payload_notes,
        "created_at": int(time.time()),
        "mode": "test_simulation",
    }
    logger.info(f"Created simulated Razorpay test order: {mock_order_id}")
    return mock_order


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """Verify webhook or callback signature using Razorpay secret."""
    client = get_razorpay_client()
    if not client:
        # Simulation mode succeeds automatically
        return True
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
        return True
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False


def create_razorpay_payment_link(
    order_id: str,
    amount_inr: float,
    receipt_id: str,
    callback_url: str = "http://localhost:8501",
) -> dict[str, Any]:
    """
    Generate a hosted Razorpay checkout link URL.
    If live keys are configured, uses client.payment_link.create.
    Otherwise generates the Razorpay test checkout page URL.
    """
    client = get_razorpay_client()
    amount_paise = int(round(amount_inr * 100))

    if client:
        try:
            payload = {
                "amount": amount_paise,
                "currency": "INR",
                "accept_partial": False,
                "reference_id": order_id,
                "description": f"TechMart Payment for {order_id}",
                "customer": {
                    "name": "TechMart Customer",
                    "email": "customer@techmart.com",
                    "contact": "+919876543210",
                },
                "notify": {"sms": False, "email": False},
                "reminder_enable": False,
                "notes": {"order_id": order_id, "receipt_id": receipt_id},
                "callback_url": f"{callback_url}?payment_status=success&order_id={order_id}",
                "callback_method": "get",
            }
            res = client.payment_link.create(data=payload)
            return {
                "payment_url": res.get("short_url"),
                "payment_link_id": res.get("id"),
                "mode": "live_test",
            }
        except Exception as e:
            logger.error(f"Live payment link creation failed: {e}. Using hosted gateway view.")

    # Hosted Razorpay Gateway Route in TechMart
    return {
        "payment_url": f"?page=razorpay_checkout&order_id={order_id}",
        "payment_link_id": f"plink_test_{uuid.uuid4().hex[:10]}",
        "mode": "test_simulation",
    }


def get_razorpay_checkout_config(
    order_id: str,
    amount_inr: float,
    receipt_id: str,
    rzp_order_id: str | None = None,
    customer_name: str = "TechMart Customer",
    customer_email: str = "customer@techmart.com",
    customer_phone: str = "9876543210",
) -> dict[str, Any]:
    """
    Generate standard Razorpay checkout configuration options
    compatible with official checkout.razorpay.com/v1/checkout.js.
    """
    amount_paise = int(round(amount_inr * 100))
    key_id = RAZORPAY_KEY_ID or "rzp_test_simulation"

    return {
        "key": key_id,
        "amount": amount_paise,
        "currency": "INR",
        "name": "TechMart AI Commerce Ltd.",
        "description": f"Payment for Order #{order_id}",
        "image": "https://cdn.razorpay.com/logos/7K3b6d1PXnYDHe_medium.png",
        "order_id": rzp_order_id or f"order_rzp_{uuid.uuid4().hex[:14]}",
        "receipt": receipt_id,
        "prefill": {
            "name": customer_name,
            "email": customer_email,
            "contact": customer_phone,
        },
        "theme": {
            "color": "#3395ff",
            "backdrop_color": "#0c2340",
        },
        "modal": {
            "backdropclose": False,
            "escape": True,
            "handleback": True,
        },
    }

