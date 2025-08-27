# app/enterprise.py
import os
import re
from typing import Optional, Dict, Any, Iterable

import psycopg
from psycopg.rows import dict_row

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

RANK = {"Enterprise-Standard": 40, "Enterprise-Professional": 50, "Enterprise-Unlimited": 60}

def _connect():
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL/DB_URL is not set")
    return psycopg.connect(url, row_factory=dict_row)

def _extract_domain(email: str) -> Optional[str]:
    email = (email or "").strip().lower()
    return email.split("@", 1)[1] if "@" in email else None

def _plan_from_en_sku(sku: str) -> Optional[str]:
    s = (sku or "").lower().strip()
    if not s.startswith("en_"):
        return None
    if "unlimited" in s:
        return "Enterprise-Unlimited"
    if "professional" in s or "pro" in s:
        return "Enterprise-Professional"
    return "Enterprise-Standard"

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

def entitlements_for_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Determine enterprise entitlement by checking active subscriptions for this email
    whose SKU starts with 'en_'.
    """
    email = (email or "").strip().lower()
    if not email:
        return None

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
    domain = _extract_domain(email) or "unknown"
    feats = _features_for(plan)

    return {
        "scope": "enterprise",
        "company": domain,
        "company_domain": domain,
        "plan": plan,
        "seats_limit": feats.get("seats_limit"),
        "features": feats,
        "expires_at": None,
        "source": "db",
    }

def entitlements_for_domain(domain: str) -> Optional[Dict[str, Any]]:
    """
    Company-level check: any active 'en_' SKU for users belonging to this domain.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return None

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
        "source": "db",
    }

# Keep webhook hook for compatibility with main.py (no-op here)
def apply_thrivecart_event(payload: Dict[str, Any]):  # type: ignore[valid-type]
    return None
