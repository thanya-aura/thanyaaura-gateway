import os
import psycopg
from psycopg.rows import dict_row

# Database connection helper
def _connect():
    return psycopg.connect(os.environ.get("DB_URL"), row_factory=dict_row)

# ---------- Existing Functions ----------
def ping_db():
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return True
    except Exception:
        return False

def upsert_subscription_and_entitlement(user_email: str, sku: str, status: str):
    # simplified example
    pass

def upsert_tier_subscription(user_email: str, tier: str, status: str):
    pass

def cancel_subscription(user_email: str):
    pass

def fetch_subscriptions(user_email: str):
    pass

def fetch_effective_agents(user_email: str):
    pass

# ---------- Trial Users ----------
def get_trial_users_by_day(day_offset: int = 0):
    """
    Return list of trial users that started exactly `day_offset` days ago.
    Example: day_offset=0 -> today, 1 -> yesterday, etc.
    """
    sql = """
        SELECT user_email, created_at
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

__all__ = [
    "ping_db",
    "upsert_subscription_and_entitlement",
    "upsert_tier_subscription",
    "cancel_subscription",
    "fetch_subscriptions",
    "fetch_effective_agents",
    "get_trial_users_by_day",
]
