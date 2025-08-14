# app/db.py — psycopg v3 DB layer for agents & tiers

from __future__ import annotations
import os
from typing import Optional, List, Dict, Any
import psycopg

# เอเจนต์ที่เป็น "รายเอเจนต์" (ไม่ใช่ tier)
DIRECT_AGENT_SLUGS = {
    'SINGLE_CF_AI_AGENT','PROJECT_CF_AI_AGENT','ENTERPRISE_CF_AI_AGENT',
    'REVENUE_STANDARD','REVENUE_INTERMEDIATE','REVENUE_ADVANCE',
    'CAPEX_STANDARD','CAPEX_PLUS','CAPEX_PREMIUM',
    'FX_STANDARD','FX_PLUS','FX_PREMIUM',
    'COST_STANDARD','COST_PLUS','COST_PREMIUM',
    'BUDGET_STANDARD','BUDGET_PLUS','BUDGET_PREMIUM',
    'REPORT_STANDARD','REPORT_PLUS','REPORT_PREMIUM',
    'VARIANCE_STANDARD','VARIANCE_PLUS','VARIANCE_PREMIUM',
    'MARGIN_STANDARD','MARGIN_PLUS','MARGIN_PREMIUM',
    'FORECAST_STANDARD','FORECAST_PLUS','FORECAST_PREMIUM',
    'DECISION_STANDARD','DECISION_PLUS','DECISION_PREMIUM',
}

def _get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Render Postgres ส่วนใหญ่ต้องการ SSL
    if "sslmode=" not in url:
        url = url + ("&" if "?" in url else "?") + "sslmode=require"
    return url

def _connect():
    return psycopg.connect(_get_db_url(), autocommit=True)

# ---------- Diagnostics ----------
def ping_db() -> Dict[str, Any]:
    """
    ทดสอบต่อ DB + ดูว่ามีตารางหลัก ๆ ไหม
    """
    info: Dict[str, Any] = {"ok": False, "error": None, "has": {}}
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.execute("""
                SELECT tablename FROM pg_catalog.pg_tables
                WHERE schemaname NOT IN ('pg_catalog','information_schema');
            """)
            names = {r[0] for r in cur.fetchall()}
            info["has"]["subscriptions"] = "subscriptions" in names
            info["has"]["agent_entitlements"] = "agent_entitlements" in names
            info["has"]["tier_entitlements"] = "tier_entitlements" in names
        info["ok"] = True
    except Exception as e:
        info["error"] = str(e)
    return info

# ---------- Upserts ----------
def upsert_subscription_and_entitlement(
    order_id: str,
    email: str,
    short_sku: str,
    agent_slug: Optional[str],
    status: str = "active",
    expires_at: Optional[str] = None,
) -> None:
    """
    - upsert ลงตาราง subscriptions (sku เก็บแบบ 'cfp', 'revs', 'premium', ฯลฯ)
    - ถ้าเป็นรายเอเจนต์ → upsert ลง agent_entitlements
    """
    if not order_id or not email or not short_sku:
        raise ValueError("order_id, email, short_sku are required")

    with _connect() as conn, conn.cursor() as cur:
        # subscriptions
        cur.execute(
            """
            INSERT INTO subscriptions (id, user_email, sku, status, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
              SET user_email = EXCLUDED.user_email,
                  sku        = EXCLUDED.sku,
                  status     = EXCLUDED.status,
                  expires_at = EXCLUDED.expires_at,
                  updated_at = NOW();
            """,
            (order_id, email, short_sku, status, expires_at),
        )

        # agent entitlement (เฉพาะสินค้ารายเอเจนต์)
        if agent_slug and agent_slug in DIRECT_AGENT_SLUGS and status == "active":
            cur.execute(
                """
                INSERT INTO agent_entitlements (user_email, agent_slug, source_subscription_id, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_email, agent_slug) DO UPDATE
                  SET source_subscription_id = EXCLUDED.source_subscription_id,
                      expires_at            = EXCLUDED.expires_at,
                      updated_at            = NOW();
                """,
                (email, agent_slug, order_id, expires_at),
            )

def upsert_tier_subscription(
    order_id: str,
    email: str,
    short_sku: str,          # 'standard' | 'plus' | 'premium' (แบบสั้น)
    tier_code: str,          # 'STANDARD' | 'PLUS' | 'PREMIUM' (แบบ canonical)
    status: str = "active",
    expires_at: Optional[str] = None,
) -> None:
    """
    - upsert subscription ของ tier (ไม่แตะ agent_entitlements)
    - effective_agents() จะรวมสิทธิ์ตาม tier_entitlements เอง
    """
    if not order_id or not email or not short_sku or not tier_code:
        raise ValueError("order_id, email, short_sku, tier_code are required")

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO subscriptions (id, user_email, sku, status, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
              SET user_email = EXCLUDED.user_email,
                  sku        = EXCLUDED.sku,
                  status     = EXCLUDED.status,
                  expires_at = EXCLUDED.expires_at,
                  updated_at = NOW();
            """,
            (order_id, email, short_sku, status, expires_at),
        )

# ---------- Cancellation ----------
def cancel_subscription(order_id: str) -> None:
    """Soft-cancel และหมดอายุ entitlement ที่ผูกกับ order_id"""
    if not order_id:
        raise ValueError("order_id is required")

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE subscriptions SET status='canceled', updated_at=NOW() WHERE id=%s;",
            (order_id,),
        )
        cur.execute(
            """
            UPDATE agent_entitlements
               SET expires_at = NOW(), updated_at=NOW()
             WHERE source_subscription_id=%s
               AND (expires_at IS NULL OR expires_at > NOW());
            """,
            (order_id,),
        )

# ---------- Diagnostics (optional) ----------
def fetch_subscriptions(email: str) -> List[tuple]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_email, sku, status, expires_at, created_at, updated_at
              FROM subscriptions
             WHERE lower(user_email)=lower(%s)
             ORDER BY created_at DESC;
            """,
            (email,),
        )
        return cur.fetchall()

def fetch_effective_agents(email: str) -> List[str]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM effective_agents(%s);", (email,))
        return [row[0] for row in cur.fetchall()]

__all__ = [
    "ping_db",
    "upsert_subscription_and_entitlement",
    "upsert_tier_subscription",
    "cancel_subscription",
    "fetch_subscriptions",
    "fetch_effective_agents",
]
