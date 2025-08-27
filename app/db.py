import os
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

# Database connection helper
def _connect():
    return psycopg.connect(os.environ.get("DB_URL"), row_factory=dict_row)

# ---------- Utility ----------
def _upsert(sql: str, params: tuple):
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return True
    except Exception as ex:
        print(f"DB error: {ex}")
        return False

# ---------- Health ----------
def ping_db():
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return True
    except Exception:
        return False

# ---------- Subscriptions ----------
def upsert_subscription_and_entitlement(order_id: str, user_email: str, sku: str, agent_slug: str, platform: str, status: str = "active"):
    """
    Store subscription for a specific agent (GPT/Gemini/Copilot).
    Uses id as unique key (tc-agent-{sku}).
    """
    sql = """
        INSERT INTO subscriptions (id, order_id, user_email, sku, agent_slug, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET agent_slug = EXCLUDED.agent_slug,
                      platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    db_id = f"tc-agent-{sku}"
    return _upsert(sql, (db_id, order_id, user_email, sku, agent_slug, platform, status))

def upsert_tier_subscription(order_id: str, user_email: str, sku: str, tier: str, platform: str, status: str = "active"):
    """
    Store subscription for a tier plan (Standard / Plus / Premium).
    Uses id as unique key (tc-tier-{sku}).
    """
    sql = """
        INSERT INTO subscriptions (id, order_id, user_email, sku, tier, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET tier       = EXCLUDED.tier,
                      platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    db_id = f"tc-tier-{sku}"
    return _upsert(sql, (db_id, order_id, user_email, sku, tier, platform, status))

def upsert_enterprise_license(order_id: str, user_email: str, sku: str, license_type: str, platform: str, status: str = "active"):
    """
    Store Copilot enterprise license (en_standard, en_professional, en_unlimited).
    Uses id as unique key (tc-ent-{sku}).
    """
    sql = """
        INSERT INTO subscriptions (id, order_id, user_email, sku, tier, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET tier       = EXCLUDED.tier,
                      platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    db_id = f"tc-ent-{sku}"
    return _upsert(sql, (db_id, order_id, user_email, sku, license_type, platform, status))

def cancel_subscription(user_email: str, sku: str = None):
    """
    Cancel one or all subscriptions for a user.
    """
    if sku:
        sql = "UPDATE subscriptions SET status = 'cancelled', updated_at = now() WHERE user_email = %s AND sku = %s"
        return _upsert(sql, (user_email, sku))
    else:
        sql = "UPDATE subscriptions SET status = 'cancelled', updated_at = now() WHERE user_email = %s"
        return _upsert(sql, (user_email,))

def fetch_subscriptions(user_email: str):
    """
    Return all subscriptions for a user.
    """
    sql = "SELECT * FROM subscriptions WHERE user_email = %s"
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (user_email,))
            return cur.fetchall()
    except Exception as ex:
        print(f"DB error: {ex}")
        return []

def fetch_effective_agents(user_email: str):
    """
    Return active agent entitlements for a user.
    """
    sql = """
        SELECT agent_slug
          FROM subscriptions
         WHERE user_email = %s
           AND status = 'active'
           AND agent_slug IS NOT NULL
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (user_email,))
            return [row["agent_slug"] for row in cur.fetchall()]
    except Exception as ex:
        print(f"DB error: {ex}")
        return []

# ---------- Trial Users ----------
def get_trial_users_by_day(day_offset: int = 0):
    """
    Return list of trial users that started exactly `day_offset` days ago.
    Includes platform for platform-aware emails.
    """
    sql = """
        SELECT user_email, created_at, platform
          FROM subscriptions
         WHERE sku = 'trial'
           AND status = 'active'
           AND DATE(created_at) = CURRENT_DATE - %s::int;
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (day_offset,))
            return cur.fetchall()
    except Exception as ex:
        print(f"DB error: {ex}")
        return []

__all__ = [
    "ping_db",
    "upsert_subscription_and_entitlement",
    "upsert_tier_subscription",
    "upsert_enterprise_license",
    "cancel_subscription",
    "fetch_subscriptions",
    "fetch_effective_agents",
    "get_trial_users_by_day",
]
