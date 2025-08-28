# app/enterprise_access.py
from typing import Optional, List, Dict, Any
from app import db

ENTERPRISE_SKUS = {"en_standard", "en_professional", "en_unlimited"}

# --- ใช้ map จาก agents ถ้ามี (ไว้ match sku->slug) ---
try:
    from app.agents import AGENT_SKU_TO_AGENT as _SKU2SLUG  # type: ignore
except Exception:
    _SKU2SLUG = {
        "cfs": "SINGLE_CF_AI_AGENT",
        "cfp": "PROJECT_CF_AI_AGENT",
        "cfpr": "ENTERPRISE_CF_AI_AGENT",
        "revs": "REVENUE_STANDARD", "revp": "REVENUE_INTERMEDIATE", "revpr": "REVENUE_ADVANCE",
        "capexs": "CAPEX_STANDARD", "capexp": "CAPEX_PLUS", "capexpr": "CAPEX_PREMIUM",
        "fxs": "FX_STANDARD", "fxp": "FX_PLUS", "fxpr": "FX_PREMIUM",
        "costs": "COST_STANDARD", "costp": "COST_PLUS", "costpr": "COST_PREMIUM",
        "buds": "BUDGET_STANDARD", "budp": "BUDGET_PLUS", "budpr": "BUDGET_PREMIUM",
        "reps": "REPORT_STANDARD", "repp": "REPORT_PLUS", "reppr": "REPORT_PREMIUM",
        "vars": "VARIANCE_STANDARD", "varp": "VARIANCE_PLUS", "varpr": "VARIANCE_PREMIUM",
        "mars": "MARGIN_STANDARD", "marp": "MARGIN_PLUS", "marpr": "MARGIN_PREMIUM",
        "fors": "FORECAST_STANDARD", "forp": "FORECAST_PLUS", "forpr": "FORECAST_PREMIUM",
        "decs": "DECISION_STANDARD", "decp": "DECISION_PLUS", "decpr": "DECISION_PREMIUM",
        "en_standard": "ENTERPRISE_LICENSE_STANDARD",
        "en_professional": "ENTERPRISE_LICENSE_PRO",
        "en_unlimited": "ENTERPRISE_LICENSE_UNLIMITED",
    }

# สร้าง inverse: slug -> {skus...} รวม alias *_gemini / *_ms / module-0-*
_AGENT2SKUS: Dict[str, set] = {}
for sku, slug in (_SKU2SLUG or {}).items():
    s = (sku or "").lower()
    if s.startswith("module-0-"):
        s = s[9:]
    _AGENT2SKUS.setdefault(slug, set()).add(s)
    _AGENT2SKUS[slug].add(f"{s}_gemini")
    _AGENT2SKUS[slug].add(f"{s}_ms")

# ---------- helpers ----------
def _email_domain(email: str) -> Optional[str]:
    try:
        return email.split("@", 1)[1].lower()
    except Exception:
        return None

def _normalize_platform(p: Optional[str]) -> str:
    s = (p or "").strip()
    if s.startswith("Copilot"):
        return "Copilot"
    return s or "GPT"

def _platform_match(request_platform: str, row_platform: Optional[str]) -> bool:
    return _normalize_platform(request_platform) == _normalize_platform(row_platform)

def _tier_from_slug(agent_slug: str) -> str:
    s = (agent_slug or "").upper()
    if s.endswith("_PREMIUM") or s.endswith("_ADVANCE"):
        return "PREMIUM"
    if s.endswith("_PLUS") or s.endswith("_INTERMEDIATE"):
        return "PLUS"
    return "STANDARD"

_TIER_ORDER = {"STANDARD": 0, "PLUS": 1, "PREMIUM": 2}

def _tier_allows(owned: str, required: str) -> bool:
    return _TIER_ORDER.get((owned or "").upper(), -1) >= _TIER_ORDER.get((required or "").upper(), 0)

def _is_active(row: Dict[str, Any]) -> bool:
    """
    ทนทุกรูปแบบ status:
      - "active"/"ACTIVE"/"Active"
      - True/1/"1"/"yes"
      - ไม่มีคีย์ status -> ถือว่า active
    """
    if "status" not in row:
        return True
    v = row.get("status")
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"active", "1", "true", "yes"}

def _best_owned_tier(rows: List[Dict[str, Any]], platform: str) -> Optional[str]:
    """
    หา tier สูงสุดของผู้ใช้บน platform จาก tier_subscriptions
    รองรับคีย์: 'tier', 'tier_code', หรือ 'sku' (เช่น PLUS / PREMIUM)
    """
    best_tier, best_rank = None, -1
    for r in rows or []:
        if not _is_active(r):
            continue
        if not _platform_match(platform, r.get("platform")):
            continue
        raw = (r.get("tier") or r.get("tier_code") or r.get("sku") or "").upper()
        if raw.startswith("TIER_"):
            raw = raw[5:]
        rank = _TIER_ORDER.get(raw, -1)
        if rank > best_rank:
            best_rank, best_tier = rank, raw
    return best_tier

def _agent_skus_for_slug(agent_slug: str) -> List[str]:
    return sorted(list(_AGENT2SKUS.get(agent_slug, set())))

# ---------- main gate ----------
def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    เงื่อนไขผ่าน (แพลตฟอร์มใดก็ได้: GPT/Gemini/Copilot):
      1) subscriptions (รายบุคคล)
         - มี sku='all' + platform ตรง -> ผ่าน
         - มี agent_slug/agent/agent_id ตรง -> ผ่าน
         - มี sku ที่ match agent (จากตาราง map) + platform ตรง -> ผ่าน
      2) tier_subscriptions (รายบุคคล)
         - STANDARD อนุญาตเฉพาะ STANDARD
         - PLUS     อนุญาต STANDARD+PLUS
         - PREMIUM  อนุญาตทั้งหมด
      3) enterprise license (โดเมน Copilot เท่านั้น)
         - en_standard: เฉพาะ agent ที่ต้องการ STANDARD
         - en_professional, en_unlimited: ทุก tier
    """
    platform = _normalize_platform(platform)
    agent_required_tier = _tier_from_slug(agent_slug)
    skus_for_agent = set(_agent_skus_for_slug(agent_slug))

    # 1) รายบุคคล: subscriptions
    try:
        subs = db.fetch_subscriptions(user_email) or []
    except Exception:
        subs = []
    for r in subs:
        if not _is_active(r):
            continue
        if not _platform_match(platform, r.get("platform")):
            continue
        sku = (r.get("sku") or "").lower().replace("module-0-", "")
        if sku == "all":
            return True
        row_agent_slug = r.get("agent_slug") or r.get("agent") or r.get("agent_id")
        if row_agent_slug and str(row_agent_slug).upper() == agent_slug.upper():
            return True
        if sku and sku in skus_for_agent:
            return True

    # 2) รายบุคคล: tier_subscriptions
    try:
        tier_rows = db.fetch_tier_subscriptions(user_email) or []
    except Exception:
        tier_rows = []
    owned_tier = _best_owned_tier(tier_rows, platform)
    if owned_tier and _tier_allows(owned_tier, agent_required_tier):
        return True

    # 3) Enterprise (Copilot only)
    if platform == "Copilot":
        domain = _email_domain(user_email)
        if domain:
            ent = db.get_active_enterprise_license_for_domain(domain)
            if ent and _platform_match(platform, ent.get("platform")):
                lic = (ent.get("sku") or "").lower()
                if lic == "en_standard":
                    return agent_required_tier == "STANDARD"
                if lic in ("en_professional", "en_unlimited"):
                    return True

    return False
