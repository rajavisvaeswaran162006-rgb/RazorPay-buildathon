"""
audit.py — TechMart AI Shopping Agent
======================================
Audit logging module for tracking agent decisions, guardrails, searches,
recommendations, upsells, and cart additions.

Stores all events in the SQLite `audit_logs` table for compliance & demo transparency.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Any
from database import get_connection

logger = logging.getLogger(__name__)


def log_event(
    event_type: str,
    action: str,
    details: str = "",
    status: str = "SUCCESS",
    rule_or_tool: str = "AI Shopping Agent",
) -> bool:
    """
    Record an agent action or guardrail check into the audit_logs table.

    Parameters
    ----------
    event_type   : USER_REQUEST | PRODUCT_SEARCH | PRODUCT_RECOMMENDATION | UPSELL_SUGGESTED | PRODUCT_ADDED_TO_CART | GUARDRAIL_CHECK
    action       : Brief action summary (e.g., 'Customer query received', 'AI recommended HP 15s')
    details      : Context details (e.g., 'Budget: ₹70,000; Category: Laptops; Purpose: coding')
    status       : Status or evaluation ('SUCCESS', 'PASSED', 'REJECTED', 'FALLBACK')
    rule_or_tool : Component triggering the log ('AI Shopping Agent', 'SQLite Search', 'Cart')
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs (timestamp, event_type, action, rule_or_tool, details, detail, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, event_type, action, rule_or_tool, details, details, status),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to write audit log: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_recent_logs(limit: int = 20) -> list[dict[str, Any]]:
    """
    Retrieve the most recent audit log entries ordered by id descending.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, event_type, action, rule_or_tool, COALESCE(details, detail, '') as details, status
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch audit logs: {e}")
        return []
    finally:
        if conn:
            conn.close()


def clear_audit_logs() -> bool:
    """Clear all audit logs (useful for demo resets)."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_logs")
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to clear audit logs: {e}")
        return False
    finally:
        if conn:
            conn.close()
