# app/entitlements.py
import os, json, logging
from datetime import datetime, date
from typing import Dict, Optional, Any, List, Tuple

from fastapi import HTTPException

# โมดูลเดิมของคุณ (ยังคงเรียกก่อน ถ้า error ค่อย fallback DB)
from app import enterprise, individual  # noqa

# เพิ่ม psycopg สำหรับ fallback DB query แบบปลอดภัย
import psycopg

log = logging.getLogger("thanyaaura.entitlements")

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

# --------------------- Fallback DB helpers (ใหม่) ---------------------
def _db_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL/DB_URL is not set")
    return url

def _connect():
    # psycopg3
    return psycopg.connect(_db_url(), autocommit=True)

def _fetch_agent_entitlements(email: str) -> List[Tuple[str, str]]:
    """
    คืนรายการ (agent_slug_or_sku, platform)
    พยายามอ่านคอลัมน์ agent_slug ก่อน ถ้าไม่มีให้ลอง sku
    """
    rows: List[Tuple[str, str]] = []
    with _connect() as conn:
        with conn.cursor() as cur:
            # agent_slug ถ้ามี
            try:
                cur.execute(
                    """
                    SELECT agent_slug, platform
                    FROM entitlements
                    WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email,),
                )
                for r in cur.fetchall():
                    if r and r[0]:
                        rows.append((r[0], r[1]))
            except Exception as e:
                log.debug("fallback: entitlements.agent_slug query failed: %s", e)

            # sku เผื่อโครงสร้างตารางใช้ sku แทน agent_slug
            try:
                cur.execute(
                    """
                    SELECT sku, platform
                    FROM entitlements
                    WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email,),
                )
                for r in cur.fetchall():
                    if r and r[0]:
                        rows.append((r[0], r[1]))
            except Exception as e:
                log.debug("fallback: entitlements.sku query failed: %s", e)
    return rows

def _fetch_tier_subscriptions(email: str) -> List[Tuple[str, str]]:
    """
    คืนรายการ (tier_code, platform) เช่น ('STANDARD'|'PLUS'|'PREMIUM', 'GPT'|'Copilot'...)
    """
    rows: List[Tuple[str, str]] = []
    with _connect() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT tier_code, platform
                    FROM tier_subscriptions
                    WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email,),
                )
                for r in cur.fetchall():
                    if r and r[0]:
                        rows.append((r[0], r[1]))
            except Exception as e:
                log.debug("fallback: tier_subscriptions query failed: %s", e)
    return rows

def _fetch_enterprise_licenses(email: str) -> List[Tuple[str, str]]:
    """
    คืนรายการ (sku, platform) เช่น ('en_standard'|'en_professional'|'en_unlimited', 'Copilot-Enterprise'|...)
    """
    rows: List[Tuple[str, str]] = []
    with _connect() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT sku, platform
                    FROM enterprise_licenses
                    WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email,),
                )
                for r in cur.fetchall():
                    if r and r[0]:
                        rows.append((r[0], r[1]))
            except Exception as e:
                log.debug("fallback: enterprise_licenses query failed: %s", e)
    return rows

def _plan_from_en_sku(sku: str) -> Optional[str]:
    s = (sku or "").lower().strip()
    if s == "en_standard":
        return "Enterprise-Standard"
    if s == "en_professional":
        return "Enterprise-Professional"
    if s == "en_unlimited":
        return "Enterprise-Unlimited"
    return None

def _plan_from_tier_code(tier_code: str) -> Optional[str]:
    t = (tier_code or "").upper().strip()
    if t == "STANDARD":
        return "Standard"
    if t == "PLUS":
        return "Plus"
    if t == "PREMIUM":
        return "Premium"
    return None

def _resolve_enterprise_fallback(email: str) -> Optional[Dict[str, Any]]:
    rows = _fetch_enterprise_licenses(email)
    if not rows:
        return None

    # เลือกแผน Enterprise สูงสุด
    best_plan = None
    for sku, _pf in rows:
        p = _plan_from_en_sku(sku)
        if p and (_rank(p) > _rank(best_plan)):
            best_plan = p

    ent: Dict[str, Any] = {
        "email": email,
        "plan": best_plan,
        "features": {},
        "company": None,
        "company_domain": None,
        "seats_limit": None,
        "expires_at": None,
        "source": "enterprise",
        "row": None,
        "agents": None,
    }
    return ent if best_plan else None

def _resolve_individual_fallback(email: str) -> Optional[Dict[str, Any]]:
    # ใช้ tier เป็นหลัก ถ้าไม่มี tier แต่มี agent entitlement จะ default เป็น Standard
    tiers = _fetch_tier_subscriptions(email)
    agents = _fetch_agent_entitlements(email)

    best_plan = None
    for tier_code, _pf in tiers:
        p = _plan_from_tier_code(tier_code)
        if p and (_rank(p) > _rank(best_plan)):
            best_plan = p

    if not best_plan:
        # ไม่มี tier แต่มี agent-level → Default เป็น Standard (ตามคอมเมนต์เดิม)
        if agents:
            best_plan = "Standard"

    ent: Dict[str, Any] = {
        "email": email,
        "plan": best_plan,
        "features": {},
        "company": None,
        "company_domain": None,
        "seats_limit": None,
        "expires_at": None,
        "source": "individual",
        "row": None,
        "agents": [{"name": a, "platform": pf} for (a, pf) in agents] if agents else None,
    }
    return ent if best_plan else None

# --------------------- Resolver (ของเดิม + fallback) ---------------------
def resolve_entitlements(email: str, precedence: str = "rank") -> Dict:
    """
    Decide user's active entitlement from DB-only data:
    - If any active SKU starts with 'en_' -> Enterprise (highest plan wins)
    - Else -> Individual (highest tier if present; otherwise defaults to Standard)
    precedence: 'enterprise' (enterprise wins) or 'rank' (higher plan rank wins)
    """
    # ขั้นแรก: ใช้ module เดิมของคุณ
    ent_e = None
    ent_i = None

    try:
        ent_e = enterprise.entitlements_for_email(email)
    except Exception as e:
        log.warning("enterprise.entitlements_for_email failed: %s", e)
        ent_e = None

    try:
        ent_i = individual.entitlements_for_email(email)
    except Exception as e:
        log.warning("individual.entitlements_for_email failed: %s", e)
        ent_i = None

    # ถ้าโมดูลเดิมให้ error หรือ None → fallback DB
    if not ent_e:
        try:
            ent_e = _resolve_enterprise_fallback(email)
        except Exception as e:
            log.warning("enterprise fallback failed: %s", e)
            ent_e = None

    if not ent_i:
        try:
            ent_i = _resolve_individual_fallback(email)
        except Exception as e:
            log.warning("individual fallback failed: %s", e)
            ent_i = None

    # ตรรกะรวมผล (เหมือนเดิม)
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

# ---------- Guard (เดิม) ----------
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
    """
    NOTE: ฟังก์ชันนี้ยังคงรูปแบบเดิมของคุณไว้ (raise HTTPException) สำหรับโค้ดส่วนอื่นที่อาจเรียกใช้
    main.py ปัจจุบันของคุณใช้ gating จาก app.enterprise_access.check_entitlement (คนละตัว)
    แต่เรายังคงตัวนี้ไว้เพื่อความเข้ากันได้ย้อนหลัง
    """
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
