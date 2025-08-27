# app/db.py
import os
import psycopg
from psycopg.rows import dict_row

# ---------- Connection ----------
def _connect():
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL/DB_URL is not set")
    return psycopg.connect(url, row_factory=dict_row)

# ---------- Helpers ----------
def _upsert(sql: str, params: tuple) -> bool:
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

# ---------- Subscriptions (align with main.py webhook) ----------
def upsert_subscription_and_entitlement(
    order_id: str,
    user_email: str,
    sku: str,
    agent_slug: str | None,
    platform: str,
    status: str = "active",
):
    """
    Store subscription for a specific agent purchase.
    ID is tied to order to avoid collision on repeat buys.
    """
    sub_id = f"tc-agent-{order_id}-{sku}-{platform}".lower()
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    return _upsert(sql, (sub_id, user_email, sku, platform, status))

def upsert_tier_subscription(
    order_id: str,
    user_email: str,
    sku: str,
    tier: str,
    platform: str,
    status: str = "active",
):
    """
    Store subscription for tier plans (Standard / Plus / Premium).
    """
    sub_id = f"tc-tier-{order_id}-{tier}-{platform}".lower()
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    return _upsert(sql, (sub_id, user_email, sku, platform, status))

def upsert_enterprise_license(
    order_id: str,
    user_email: str,
    sku: str,                 # e.g., en_standard, en_professional, en_unlimited
    agent_slug: str | None,   # not used here; kept for signature parity
    platform: str,
    status: str = "active",
):
    """
    Store Copilot enterprise license (en_standard / en_professional / en_unlimited).
    """
    license_type = (sku or "").lower()
    sub_id = f"tc-enterprise-{order_id}-{license_type}-{platform}".lower()
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    return _upsert(sql, (sub_id, user_email, sku, platform, status))

def cancel_subscription(user_email: str, sku: str | None = None):
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
    If sku = 'all', return all 33 agents.
    """
    sql = """
        SELECT sku, platform, status
          FROM subscriptions
         WHERE user_email = %s
           AND status = 'active';
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (user_email,))
            rows = cur.fetchall()

            # If permanent "all" entitlement is found, return all agents
            for row in rows:
                if row["sku"] == "all":
                    return [
                        "budget_standard", "budget_plus", "budget_premium",
                        "capex_standard", "capex_plus", "capex_premium",
                        "cost_standard", "cost_plus", "cost_premium",
                        "decision_standard", "decision_plus", "decision_premium",
                        "enterprise_cf", "project_cf", "single_cf",
                        "forecast_standard", "forecast_plus", "forecast_premium",
                        "fx_standard", "fx_plus", "fx_premium",
                        "margin_standard", "margin_plus", "margin_premium",
                        "report_standard", "report_plus", "report_premium",
                        "revenue_standard", "revenue_intermediate", "revenue_advance",
                        "variance_standard", "variance_plus", "variance_premium",
                    ]
            # Otherwise return only entitled agents
            return [row["sku"] for row in rows if row["sku"] != "all"]
    except Exception as ex:
        print(f"DB error: {ex}")
        return []

# ---------- Trial Users ----------
def get_trial_users_by_day(day_offset: int = 0):
    """
    Return list of trial users whose created_at falls on Thailand's (Asia/Bangkok) date
    exactly `day_offset` days ago (0=today TH, 1=yesterday TH, etc.).
    """
    sql = """
        SELECT user_email, created_at, platform
          FROM subscriptions
         WHERE sku = 'trial'
           AND status = 'active'
           AND (created_at AT TIME ZONE 'Asia/Bangkok')::date =
               (now() AT TIME ZONE 'Asia/Bangkok')::date - %s::int;
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (day_offset,))
            return cur.fetchall()
    except Exception:
        return []

def ensure_permanent_admin_user():
    """
    Ensure thanyaaura@email.com always has permanent 'all' subscriptions
    across GPT, Gemini, and Copilot.
    """
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES
            ('perm-gpt-all', 'thanyaaura@email.com', 'all', 'GPT', 'active', now(), now()),
            ('perm-gemini-all', 'thanyaaura@email.com', 'all', 'Gemini', 'active', now(), now()),
            ('perm-copilot-all', 'thanyaaura@email.com', 'all', 'Copilot', 'active', now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = 'active',
                      updated_at = now();
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
            print("✅ Permanent admin user ensured in DB")
            return True
    except Exception as ex:
        print(f"DB error ensuring permanent admin user: {ex}")
        return False

__all__ = [
    "ping_db",
    "upsert_subscription_and_entitlement",
    "upsert_tier_subscription",
    "upsert_enterprise_license",
    "cancel_subscription",
    "fetch_subscriptions",
    "fetch_effective_agents",
    "get_trial_users_by_day",
    "ensure_permanent_admin_user",
]
