# app/enterprise.py
import os
from typing import Optional, Dict, Any, Iterable, List

import psycopg
from psycopg.rows import dict_row

# ---------------------------------------------
# Plan definitions (คงเดิม)
# ---------------------------------------------
PLAN_FEATURES: Dict[str, Dict[str, Any]] = {
    "Enterprise-Standard": {
        "seats_limit": "seats",  # if you add seats later
        "platforms": ["GPT", "Gemini", "Copilot"],
        "api_limit": "10k/day",
        "support": "Standard",
        "export": True,
        "priority": False,
    },
    "Enterprise-Professional": {
        "seats_limit": "seats",
        "platforms": ["GPT", "Gemini", "Copilot"],
        "api_limit": "100k/day",
        "support": "Priority",
        "export": True,
        "priority": True,
    },
    "Enterprise-Unlimited": {
        "seats_limit": None,  # unlimited
        "platforms": ["GPT", "Gemini", "Copilot"],
        "api_limit": "Unlimited (fair use)",
        "support": "Priority",
        "export": True,
        "priority": True,
    },
}

RANK = {
    "Enterprise-Standard": 40,
    "Enterprise-Professional": 50,
    "Enterprise-Unlimited": 60,
}

# ---------------------------------------------
# DB utils
# ---------------------------------------------
def _connect():
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL/DB_URL is not set")
    return psycopg.connect(url, row_factory=dict_row)

def _extract_domain(email: str) -> Optional[str]:
    email = (email or "").strip().lower()
    return email.split("@", 1)[1] if "@" in email else None

# ---------------------------------------------
# Plan mapping helpers
# ---------------------------------------------
def _plan_from_en_sku(sku: str) -> Optional[str]:
    """Map en_* SKU → Enterprise-* plan name."""
    s = (sku or "").lower().strip()
    if not s.startswith("en_"):
        return None
    if "unlimited" in s:
        return "Enterprise-Unlimited"
    if "professional" in s or s.endswith("_pro") or s == "en_pro":
        return "Enterprise-Professional"
    return "Enterprise-Standard"

def _plan_from_tier_code(tier: Optional[str]) -> Optional[str]:
    """Map tier_code (STANDARD/PROFESSIONAL/UNLIMITED) → Enterprise-* plan name."""
    if not tier:
        return None
    t = tier.strip().upper()
    if t == "UNLIMITED":
        return "Enterprise-Unlimited"
    if t == "PROFESSIONAL":
        return "Enterprise-Professional"
    if t == "STANDARD":
        return "Enterprise-Standard"
    return None

def _pick_highest(plans: Iterable[str]) -> Optional[str]:
    best = None
    best_rank = -1
    for p in plans:
        r = RANK.get(p, -1)
        if r > best_rank:
            best, best_rank = p, r
    return best

def _features_for(plan: str, seats: Optional[int] = None) -> Dict[str, Any]:
    base = PLAN_FEATURES.get(plan)
    if not base:
        return {}
    out = dict(base)
    if base["seats_limit"] == "seats":
        out["seats_limit"] = seats if seats is not None else 1
    return out

# ---------------------------------------------
# Core: enterprise entitlement resolvers
# ---------------------------------------------
def _plans_from_enterprise_licenses(domain: str) -> List[str]:
    """
    อ่าน active แถวจาก enterprise_licenses ของโดเมน แล้วแปลงเป็นรายชื่อ plan
    """
    d = (domain or "").strip().lower()
    if not d:
        return []

    sql = """
        SELECT sku, tier_code, active, activated_at, expires_at
          FROM enterprise_licenses
         WHERE domain = %s
           AND active IS TRUE
         ORDER BY activated_at DESC
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (d,))
            rows = cur.fetchall()
    except Exception as ex:
        print(f"DB error (enterprise_licenses lookup): {ex}")
        return []

    plans: List[str] = []
    for r in rows:
        # ใช้ tier_code เป็นหลัก (แม่นกว่า), ถ้าไม่มีค่อย fallback จาก sku
        plan = _plan_from_tier_code(r.get("tier_code")) or _plan_from_en_sku(r.get("sku", ""))
        if plan:
            plans.append(plan)
    return plans

def entitlements_for_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Determine enterprise entitlement for a user by:
      1) PRIMARY: look up domain in enterprise_licenses (active rows)
      2) FALLBACK: look up personal 'en_%' subscriptions for that email (ของเดิม)
    """
    email = (email or "").strip().lower()
    if not email:
        return None
    domain = _extract_domain(email)
    if not domain:
        return None

    # 1) PRIMARY: enterprise_licenses by domain
    plans = _plans_from_enterprise_licenses(domain)
    if plans:
        plan = _pick_highest(plans)
        feats = _features_for(plan) if plan else {}
        return {
            "scope": "enterprise",
            "company": domain,
            "company_domain": domain,
            "plan": plan,
            "seats_limit": feats.get("seats_limit"),
            "features": feats,
            "expires_at": None,   # สามารถดึง expires_at ล่าสุดมาใส่ได้ ถ้าต้องการ
            "source": "enterprise_licenses",
        }

    # 2) FALLBACK: เดิมอ่านจาก subscriptions ของ email นี้ (en_%)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT sku
              FROM subscriptions
             WHERE user_email = %s
               AND status = 'active'
               AND sku ILIKE 'en_%'
            """,
            (email,),
        )
        rows = cur.fetchall()

    plans = [_plan_from_en_sku(r["sku"]) for r in rows if r.get("sku")]
    plans = [p for p in plans if p]
    if not plans:
        return None

    plan = _pick_highest(plans)
    feats = _features_for(plan)

    return {
        "scope": "enterprise",
        "company": domain,
        "company_domain": domain,
        "plan": plan,
        "seats_limit": feats.get("seats_limit"),
        "features": feats,
        "expires_at": None,
        "source": "subscriptions",  # fallback แสดงที่มา
    }

def entitlements_for_domain(domain: str) -> Optional[Dict[str, Any]]:
    """
    Company-level check:
      1) PRIMARY: active enterprise_licenses for this domain
      2) FALLBACK: any active 'en_%' SKU in subscriptions for users under this domain (ของเดิม)
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return None

    # 1) PRIMARY: enterprise_licenses
    plans = _plans_from_enterprise_licenses(domain)
    if plans:
        plan = _pick_highest(plans)
        feats = _features_for(plan) if plan else {}
        return {
            "scope": "enterprise",
            "company": domain,
            "company_domain": domain,
            "plan": plan,
            "seats_limit": feats.get("seats_limit"),
            "features": feats,
            "expires_at": None,
            "source": "enterprise_licenses",
        }

    # 2) FALLBACK: subscriptions (ของเดิม)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT sku
              FROM subscriptions
             WHERE user_email ILIKE %s
               AND status = 'active'
               AND sku ILIKE 'en_%'
            """,
            (f"%@{domain}",),
        )
        rows = cur.fetchall()

    plans = [_plan_from_en_sku(r["sku"]) for r in rows if r.get("sku")]
    plans = [p for p in plans if p]
    if not plans:
        return None

    plan = _pick_highest(plans)
    feats = _features_for(plan)

    return {
        "scope": "enterprise",
        "company": domain,
        "company_domain": domain,
        "plan": plan,
        "seats_limit": feats.get("seats_limit"),
        "features": feats,
        "expires_at": None,
        "source": "subscriptions",  # fallback แสดงที่มา
    }

# ---------------------------------------------
# Keep webhook hook for compatibility with main.py (no-op here)
# ---------------------------------------------
def apply_thrivecart_event(payload: Dict[str, Any]):  # type: ignore[valid-type]
    return None
