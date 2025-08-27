import os
import psycopg
from psycopg.rows import dict_row

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
def upsert_subscription_and_entitlement(user_email: str, sku: str, platform: str, status: str = "active"):
    """
    Store subscription for a specific agent or 'all' entitlement.
    """
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    sub_id = f"tc-agent-{sku}-{platform}".lower()
    return _upsert(sql, (sub_id, user_email, sku, platform, status))

def upsert_tier_subscription(user_email: str, sku: str, tier: str, platform: str, status: str = "active"):
    """
    Store subscription for a tier plan (Standard / Plus / Premium).
    """
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    sub_id = f"tc-tier-{tier}-{platform}".lower()
    return _upsert(sql, (sub_id, user_email, sku, platform, status))

def upsert_enterprise_license(user_email: str, sku: str, license_type: str, platform: str, status: str = "active"):
    """
    Store Copilot enterprise license (en_standard, en_professional, en_unlimited).
    """
    sql = """
        INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id)
        DO UPDATE SET platform   = EXCLUDED.platform,
                      status     = EXCLUDED.status,
                      updated_at = now();
    """
    sub_id = f"tc-enterprise-{license_type}-{platform}".lower()
    return _upsert(sql, (sub_id, user_email, sku, platform, status))

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
    Return list of trial users that started exactly `day_offset` days ago.
    Example: day_offset=0 -> today, 1 -> yesterday, etc.
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
]
