# app/db.py
import os
import psycopg
from psycopg.rows import dict_row

# ===== Feature flags (ของเดิม) =====
# เขียนซ้ำลง subscriptions เพื่อความเข้ากันได้ย้อนหลัง (ค่าเริ่มต้น: เปิด)
EN_DUAL_WRITE = os.getenv("EN_DUAL_WRITE", "1") == "1"
# บังคับให้โดเมนหนึ่งมี active ได้ครั้งละ 1 แผน: ปิดตัวอื่นอัตโนมัติ (ค่าเริ่มต้น: เปิด)
EN_DEACTIVATE_OTHERS = os.getenv("EN_DEACTIVATE_OTHERS", "1") == "1"

# ===== New: table names (เผื่อ future rename) =====
TBL_TENANTS          = os.getenv("TBL_TENANTS", "tenants")
TBL_API_KEYS         = os.getenv("TBL_API_KEYS", "api_keys")
TBL_SUBS_ENT         = os.getenv("TBL_SUBS_ENT", "ent_subscriptions")     # แผน ENT_STANDARD/ENT_PLUS/ENT_PRO
TBL_USAGE            = os.getenv("TBL_USAGE", "usage_counters")           # calls/yyyymm
TBL_IDEM             = os.getenv("TBL_IDEM", "idempotency_keys")

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

def _exec(sql: str, params: tuple | None = None):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        conn.commit()

def _fetchone(sql: str, params: tuple | None = None):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()

def _fetchall(sql: str, params: tuple | None = None):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()

# ---------- Ensure quota schema (lazy) ----------
def _ensure_quota_schema():
    """
    สร้างตารางที่จำเป็นสำหรับ Thin API quota/plan หากยังไม่มี
    - tenants, api_keys, ent_subscriptions, usage_counters, idempotency_keys
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TBL_TENANTS} (
              id BIGSERIAL PRIMARY KEY,
              name TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TBL_API_KEYS} (
              id BIGSERIAL PRIMARY KEY,
              tenant_id BIGINT NOT NULL REFERENCES {TBL_TENANTS}(id) ON DELETE CASCADE,
              key_hash CHAR(64) NOT NULL UNIQUE,
              active BOOLEAN NOT NULL DEFAULT TRUE,
              expires_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TBL_SUBS_ENT} (
              tenant_id BIGINT NOT NULL REFERENCES {TBL_TENANTS}(id) ON DELETE CASCADE,
              plan_code TEXT NOT NULL,                     -- ENT_STANDARD / ENT_PLUS / ENT_PRO
              monthly_quota INT NOT NULL,
              extra_quota_balance INT NOT NULL DEFAULT 0,  -- โควตาซื้อเพิ่มคงเหลือ (add-on)
              renew_day SMALLINT NOT NULL DEFAULT 1,       -- 1..28 (วันตัดรอบ)
              status TEXT NOT NULL DEFAULT 'active',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (tenant_id)
            );
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TBL_USAGE} (
              tenant_id BIGINT NOT NULL REFERENCES {TBL_TENANTS}(id) ON DELETE CASCADE,
              period_yyyymm CHAR(7) NOT NULL,              -- 'YYYY-MM'
              calls_used INT NOT NULL DEFAULT 0,
              PRIMARY KEY (tenant_id, period_yyyymm)
            );
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TBL_IDEM} (
              tenant_id BIGINT NOT NULL REFERENCES {TBL_TENANTS}(id) ON DELETE CASCADE,
              idem_key TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (tenant_id, idem_key)
            );
        """)
        conn.commit()

# ---------- Health ----------
def ping_db():
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return True
    except Exception:
        return False

# ======================================================================
# Existing (เดิม) — Subscriptions / Entitlements ที่ใช้กับ webhook ตัวเก่า
# ======================================================================
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
    sku: str,                 # en_standard | en_professional | en_unlimited
    agent_slug: str | None,   # ไม่ได้ใช้ แต่คง signature เดิม
    platform: str,
    status: str = "active",
):
    """
    บันทึกสิทธิ์ Enterprise ลง enterprise_licenses (แหล่งอ้างอิงหลัก)
    และเก็บร่องรอยไว้ใน subscriptions ตามเดิม (เพื่อความเข้ากันได้ย้อนหลัง)
    - มี option ปิดสิทธิ์แผนเก่าในโดเมนเดียวกันให้อัตโนมัติ (EN_DEACTIVATE_OTHERS)
    """
    license_type = (sku or "").strip().lower()
    tier_map = {
        "en_standard": "STANDARD",
        "en_professional": "PROFESSIONAL",
        "en_unlimited": "UNLIMITED",
    }
    tier_code = tier_map.get(license_type)
    if not tier_code:
        raise ValueError(f"bad enterprise sku: {sku!r}")

    # ดึงโดเมนจากอีเมลผู้ซื้อ
    email = (user_email or "").strip().lower()
    if "@" not in email:
        raise ValueError("bad purchaser email (no domain)")
    domain = email.split("@", 1)[1]

    # 1) อัปเซิร์ตลง enterprise_licenses (ตัวจริงที่ตัว checker ใช้อ่าน)
    sql_ent = """
        INSERT INTO enterprise_licenses (domain, sku, tier_code, active, last_order_id, activated_at, expires_at)
        VALUES (%s, %s, %s, TRUE, %s, now(), NULL)
        ON CONFLICT (domain, sku) DO UPDATE
           SET tier_code     = EXCLUDED.tier_code,
               active        = TRUE,
               last_order_id = EXCLUDED.last_order_id,
               activated_at  = now(),
               expires_at    = NULL;
    """
    ok1 = _upsert(sql_ent, (domain, license_type, tier_code, order_id))

    # 1.1) (ทางเลือก) ปิดสิทธิ์ enterprise sku อื่น ๆ ของโดเมนเดียวกัน (เหลือ active แผนล่าสุดเพียงตัวเดียว)
    ok1b = True
    if EN_DEACTIVATE_OTHERS:
        sql_deact = """
            UPDATE enterprise_licenses
               SET active = FALSE,
                   expires_at = now()
             WHERE domain = %s
               AND sku <> %s
               AND active IS TRUE;
        """
        ok1b = _upsert(sql_deact, (domain, license_type))

    # 2) (ทางเลือก) เก็บร่องรอยไว้ใน subscriptions (ตามโค้ดเดิม) เพื่อ backward compatibility
    ok2 = True
    if EN_DUAL_WRITE:
        sub_id = f"tc-enterprise-{order_id}-{license_type}-{platform}".lower()
        sql_sub = """
            INSERT INTO subscriptions (id, user_email, sku, platform, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (id)
            DO UPDATE SET platform   = EXCLUDED.platform,
                          status     = EXCLUDED.status,
                          updated_at = now();
        """
        # เขียน platform เป็น 'Copilot' ให้เป็นไปตามกติกาเดียวกันเสมอ
        ok2 = _upsert(sql_sub, (sub_id, user_email, license_type, "Copilot", "active"))

    return bool(ok1 and ok1b and ok2)

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
    (และ ensure โครงสร้างตาราง thin quota)
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
            _ensure_quota_schema()
            print("✅ Permanent admin user ensured in DB; quota schema ensured")
            return True
    except Exception as ex:
        print(f"DB error ensuring permanent admin user: {ex}")
        try:
            _ensure_quota_schema()
        except Exception as ex2:
            print(f"DB error ensuring quota schema: {ex2}")
        return False

# ======================================================================
# New for Thin API quota/plan (ใช้โดย app.limits.require_tenant_and_quota)
# ======================================================================

# --- Tenant & API key management ---
def create_or_update_tenant_with_key(name: str, api_key_hash: str, active: bool = True) -> int:
    """
    สร้าง/แก้ไข tenant + api key (hash แล้ว) — คืน tenant_id
    หมายเหตุ: api_key_hash = sha256(plain).hexdigest() (ทำในแอปก่อนส่งมา)
    """
    _ensure_quota_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO {TBL_TENANTS}(name, status) VALUES (%s,'active') RETURNING id;", (name,))
        tid = cur.fetchone()["id"]
        cur.execute(f"""
            INSERT INTO {TBL_API_KEYS}(tenant_id, key_hash, active)
            VALUES (%s, %s, %s)
            ON CONFLICT (key_hash) DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                active = EXCLUDED.active;
        """, (tid, api_key_hash, active))
        conn.commit()
        return tid

def add_or_rotate_api_key(tenant_id: int, api_key_hash: str, active: bool = True):
    _ensure_quota_schema()
    return _upsert(
        f"""
        INSERT INTO {TBL_API_KEYS}(tenant_id, key_hash, active)
        VALUES (%s,%s,%s)
        ON CONFLICT (key_hash) DO UPDATE SET
            tenant_id = EXCLUDED.tenant_id,
            active = EXCLUDED.active,
            expires_at = NULL;
        """,
        (tenant_id, api_key_hash, active),
    )

def get_tenant_by_api_key_hash(key_hash: str):
    """
    RETURN: { id, name, status, created_at } | None
    """
    _ensure_quota_schema()
    sql = f"""
        SELECT t.id, t.name, t.status, t.created_at
          FROM {TBL_API_KEYS} k
          JOIN {TBL_TENANTS} t ON t.id = k.tenant_id
         WHERE k.key_hash = %s
           AND k.active IS TRUE
           AND (k.expires_at IS NULL OR k.expires_at > now())
         LIMIT 1;
    """
    try:
        return _fetchone(sql, (key_hash,))
    except Exception as ex:
        print(f"DB error get_tenant_by_api_key_hash: {ex}")
        return None

# --- Subscription (ENT_STANDARD / ENT_PLUS / ENT_PRO) ---
def set_tenant_subscription(tenant_id: int, plan_code: str, monthly_quota: int, renew_day: int = 1, status: str = "active"):
    """
    กำหนด/อัปเดตแผน Thin ของ tenant
    plan_code: ENT_STANDARD / ENT_PLUS / ENT_PRO
    monthly_quota: จำนวน calls/เดือน
    renew_day: วันตัดรอบ (1..28) — มักตั้งตามวันชำระเงินบิลแรก
    """
    _ensure_quota_schema()
    sql = f"""
        INSERT INTO {TBL_SUBS_ENT}(tenant_id, plan_code, monthly_quota, extra_quota_balance, renew_day, status, created_at, updated_at)
        VALUES (%s, %s, %s, 0, %s, %s, now(), now())
        ON CONFLICT (tenant_id) DO UPDATE SET
            plan_code = EXCLUDED.plan_code,
            monthly_quota = EXCLUDED.monthly_quota,
            renew_day = EXCLUDED.renew_day,
            status = EXCLUDED.status,
            updated_at = now();
    """
    return _upsert(sql, (tenant_id, plan_code, monthly_quota, renew_day, status))

def add_quota_addon(tenant_id: int, addon_calls: int):
    """
    เติมโควตาเพิ่มเข้าบัญชี tenant (เช่น ซื้อ addon_1k x 3 = 3,000 calls)
    """
    _ensure_quota_schema()
    sql = f"""
        UPDATE {TBL_SUBS_ENT}
           SET extra_quota_balance = COALESCE(extra_quota_balance,0) + %s,
               updated_at = now()
         WHERE tenant_id = %s;
    """
    return _upsert(sql, (addon_calls, tenant_id))

def get_subscription_by_tenant_id(tenant_id: int):
    """
    RETURN: { tenant_id, plan_code, monthly_quota, extra_quota_balance, renew_day, status } | None
    """
    _ensure_quota_schema()
    sql = f"SELECT * FROM {TBL_SUBS_ENT} WHERE tenant_id = %s AND status = 'active' LIMIT 1;"
    try:
        return _fetchone(sql, (tenant_id,))
    except Exception as ex:
        print(f"DB error get_subscription_by_tenant_id: {ex}")
        return None

# --- Usage & Idempotency ---
def ensure_usage_bucket(tenant_id: int, yyyymm: str):
    _ensure_quota_schema()
    sql = f"""
        INSERT INTO {TBL_USAGE}(tenant_id, period_yyyymm, calls_used)
        VALUES (%s, %s, 0)
        ON CONFLICT (tenant_id, period_yyyymm) DO NOTHING;
    """
    return _upsert(sql, (tenant_id, yyyymm))

def get_calls_used(tenant_id: int, yyyymm: str) -> int:
    _ensure_quota_schema()
    sql = f"SELECT calls_used FROM {TBL_USAGE} WHERE tenant_id = %s AND period_yyyymm = %s;"
    try:
        row = _fetchone(sql, (tenant_id, yyyymm))
        return int(row["calls_used"]) if row and row.get("calls_used") is not None else 0
    except Exception as ex:
        print(f"DB error get_calls_used: {ex}")
        return 0

def increment_calls_used(tenant_id: int, yyyymm: str, amount: int) -> bool:
    _ensure_quota_schema()
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f"""
                UPDATE {TBL_USAGE}
                   SET calls_used = calls_used + %s
                 WHERE tenant_id = %s AND period_yyyymm = %s;
            """, (amount, tenant_id, yyyymm))
            if cur.rowcount == 0:
                # fallback: create bucket then retry once
                cur.execute(f"""
                    INSERT INTO {TBL_USAGE}(tenant_id, period_yyyymm, calls_used)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id, period_yyyymm) DO UPDATE SET
                        calls_used = {TBL_USAGE}.calls_used + EXCLUDED.calls_used;
                """, (tenant_id, yyyymm, amount))
            conn.commit()
            return True
    except Exception as ex:
        print(f"DB error increment_calls_used: {ex}")
        return False

def seen_idempotency(tenant_id: int, idem_key: str | None) -> bool:
    if not idem_key:
        return False
    _ensure_quota_schema()
    sql = f"SELECT 1 FROM {TBL_IDEM} WHERE tenant_id = %s AND idem_key = %s;"
    try:
        row = _fetchone(sql, (tenant_id, idem_key))
        return bool(row)
    except Exception as ex:
        print(f"DB error seen_idempotency: {ex}")
        return False

def write_idempotency(tenant_id: int, idem_key: str):
    _ensure_quota_schema()
    sql = f"""
        INSERT INTO {TBL_IDEM}(tenant_id, idem_key, created_at)
        VALUES (%s, %s, now())
        ON CONFLICT (tenant_id, idem_key) DO NOTHING;
    """
    return _upsert(sql, (tenant_id, idem_key))

# ======================================================================
# __all__
# ======================================================================
__all__ = [
    # health & legacy
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
    # thin/quota
    "create_or_update_tenant_with_key",
    "add_or_rotate_api_key",
    "set_tenant_subscription",
    "add_quota_addon",
    "get_tenant_by_api_key_hash",
    "get_subscription_by_tenant_id",
    "ensure_usage_bucket",
    "get_calls_used",
    "increment_calls_used",
    "seen_idempotency",
    "write_idempotency",
]
