# app/entitlements.py
import os, json
from datetime import datetime, date
from typing import Dict, Optional
from fastapi import HTTPException
from app import enterprise, individual

PLAN_RANK = {
    # Individual
    "Standard": 10, "Plus": 20, "Premium": 30,
    # Enterprise
    "Enterprise-Standard": 40, "Enterprise-Professional": 50, "Enterprise-Unlimited": 60,
}

def _rank(plan: Optional[str]) -> int:
    return PLAN_RANK.get(plan or "", -1)

def _normalize(ent: Dict, scope: str) -> Dict:
    return {
        "scope": scope,
        "plan": ent.get("plan"),
        "features": ent.get("features") or {},
        "company": ent.get("company"),
        "company_domain": ent.get("company_domain"),
        "seats_limit": ent.get("seats_limit"),
        "expires_at": ent.get("expires_at"),
        "source": ent.get("source", scope),
        "row": ent.get("row"),
        "email": ent.get("email"),
        "agents": ent.get("agents"),
    }

def resolve_entitlements(email: str, precedence: str = "rank") -> Dict:
    """
    Decide user's active entitlement from DB-only data:
    - If any active SKU starts with 'en_' -> Enterprise (highest plan wins)
    - Else -> Individual (highest tier if present; otherwise defaults to Standard)
    precedence: 'enterprise' (enterprise wins) or 'rank' (higher plan rank wins)
    """
    ent_e = enterprise.entitlements_for_email(email)
    ent_i = individual.entitlements_for_email(email)

    if ent_e and not ent_i:
        return _normalize(ent_e, "enterprise")
    if ent_i and not ent_e:
        return _normalize(ent_i, "individual")
    if not ent_e and not ent_i:
        return {"scope": "none", "plan": None, "features": {}, "source": "none"}

    if precedence == "enterprise":
        return _normalize(ent_e, "enterprise")

    best = ent_e if _rank(ent_e.get("plan")) >= _rank(ent_i.get("plan")) else ent_i
    scope = "enterprise" if best is ent_e else "individual"
    return _normalize(best, scope)

# ---------- Guard (optional) ----------
def _is_expired(iso: Optional[str]) -> bool:
    if not iso:
        return False
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.date() < date.today()
    except Exception:
        try:
            return datetime.strptime(iso, "%Y-%m-%d").date() < date.today()
        except Exception:
            return False

def _parse_minplan_map() -> dict:
    raw = (os.getenv("AGENT_MIN_PLAN_JSON") or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}

def _is_allowed(scope: str, plan: str, agent_slug: str) -> bool:
    """
    Optional per-agent gating via env:
    AGENT_MIN_PLAN_JSON = {
      "cashflow-standard": "Standard",
      "revenue-advanced": {"enterprise": "Enterprise-Professional", "individual": "Premium"}
    }
    """
    minmap = _parse_minplan_map()
    rule = minmap.get(agent_slug)
    if not rule:
        return True
    min_required = rule.get(scope) if isinstance(rule, dict) else str(rule)
    if not min_required:
        return True
    return _rank(plan) >= _rank(min_required)

def check_entitlement(user_id: str, agent_slug: str) -> None:
    email = user_id if user_id and "@" in user_id else (os.getenv("DEFAULT_USER_EMAIL") or None)
    if not email:
        raise HTTPException(status_code=403, detail="Email is required to resolve entitlements.")
    ent = resolve_entitlements(email, precedence=os.getenv("ENT_PRECEDENCE", "rank"))
    if ent.get("scope") == "none" or not ent.get("plan"):
        raise HTTPException(status_code=403, detail="No active plan for this user.")
    if _is_expired(ent.get("expires_at")):
        raise HTTPException(status_code=403, detail="Plan is expired.")
    if not _is_allowed(ent.get("scope"), ent.get("plan"), agent_slug):
        raise HTTPException(
            status_code=403,
            detail=f"Plan '{ent.get('plan')}' ({ent.get('scope')}) is not allowed for agent '{agent_slug}'."
        )
