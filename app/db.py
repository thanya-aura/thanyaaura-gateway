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
    Store Copilot enterprise license (en_standard / en_professional / en_unlimited)
    → บันทึกลงตาราง enterprise_licenses (PRIMARY) ไม่ใช่ subscriptions
    """
    license_type = (sku or "").lower().strip()
    if license_type not in ("en_standard", "en_professional", "en_unlimited"):
        # ไม่ใช่ enterprise sku ก็ข้าม (คงพฤติกรรมเดิมไว้)
        return False

    domain = (user_email or "").split("@")[-1].lower().strip()
    if not domain:
        print("DB warn: upsert_enterprise_license got bad purchaser email:", user_email)
        return False

    tier_code = (
        "STANDARD" if license_type == "en_standard"
        else "PROFESSIONAL" if license_type == "en_professional"
        else "UNLIMITED"
    )

    sql = """
        INSERT INTO enterprise_licenses (domain, sku, tier_code, active, activated_at, expires_at, last_order_id)
        VALUES (%s, %s, %s, TRUE, NOW(), NULL, %s)
        ON CONFLICT (domain, sku)
        DO UPDATE SET tier_code     = EXCLUDED.tier_code,
                      active        = TRUE,
                      activated_at  = NOW(),
                      expires_at    = NULL,
                      last_order_id = EXCLUDED.last_order_id;
    """
    # order_id ใช้เก็บใน last_order_id เพื่อ audit
    return _upsert(sql, (domain, license_type, tier_code, order_id))

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

# ---------- Enterprise helpers ----------
def fetch_enterprise_licenses_for_domain(domain: str):
    """
    คืนรายการ license ทั้งหมดของโดเมนจาก enterprise_licenses (สำหรับ snapshot)
    """
    d = (domain or "").lower().strip()
    if not d:
        return []
    sql = """
        SELECT domain, sku, tier_code, active, activated_at, expires_at, last_order_id
          FROM enterprise_licenses
         WHERE domain = %s
         ORDER BY activated_at DESC
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (d,))
            return cur.fetchall()
    except Exception as ex:
        print(f"DB error: {ex}")
        return []

def get_active_enterprise_license_for_domain(domain: str):
    """
    คืน license enterprise ล่าสุดของโดเมน (PRIMARY: enterprise_licenses)
    ถ้าไม่พบ ค่อย fallback ไปตาราง subscriptions (ของเก่า)
    รูปแบบรีเทิร์นให้ใกล้เคียง subscriptions เพื่อใช้กับ checker เดิม:
      { sku, platform, status, user_email, created_at, tier_code? }
    """
    d = (domain or "").lower().strip()
    if not d:
        return None

    # 1) ดูจาก enterprise_licenses ก่อน
    sql1 = """
        SELECT sku, tier_code, active, activated_at
          FROM enterprise_licenses
         WHERE domain = %s AND active IS TRUE
         ORDER BY activated_at DESC
         LIMIT 1
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql1, (d,))
            row = cur.fetchone()
            if row:
                return {
                    "sku": row["sku"],
                    "platform": "Copilot",
                    "status": "active" if row.get("active") else "inactive",
                    "user_email": f"*@{d}",
                    "created_at": row.get("activated_at"),
                    "tier_code": row.get("tier_code"),
                }
    except Exception as ex:
        print(f"DB error: {ex}")

    # 2) fallback: subscriptions (รองรับข้อมูลเก่า)
    sql2 = """
        SELECT sku, platform, status, user_email, created_at
          FROM subscriptions
         WHERE status = 'active'
           AND sku IN ('en_standard','en_professional','en_unlimited')
           AND lower(split_part(user_email,'@',2)) = lower(%s)
         ORDER BY created_at DESC
         LIMIT 1
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql2, (d,))
            return cur.fetchone()
    except Exception as ex:
        print(f"DB error: {ex}")
        return None

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
    "fetch_enterprise_licenses_for_domain",
    "get_active_enterprise_license_for_domain",
    "get_trial_users_by_day",
    "ensure_permanent_admin_user",
]
