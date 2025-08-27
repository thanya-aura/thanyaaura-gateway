# app/enterprise_access.py
from typing import Optional, List, Dict, Any
from app import db

# --- แผน Enterprise แบบโดเมน ---
ENTERPRISE_SKUS = {"en_standard", "en_professional", "en_unlimited"}

# --- พยายามใช้ตาราง map จากไฟล์ agents ถ้ามี; ถ้าไม่มี ใช้ fallback ชุดหลัก ---
try:
    # ควรมี AGENT_SKU_TO_AGENT = {"cfs": "SINGLE_CF_AI_AGENT", ...}
    from app.agents import AGENT_SKU_TO_AGENT as _SKU2SLUG  # type: ignore
except Exception:
    _SKU2SLUG = {
        # core (ย่อบางส่วนพอให้ครอบคลุม agent หลัก)
        "cfs": "SINGLE_CF_AI_AGENT",
        "cfp": "PROJECT_CF_AI_AGENT",
        "cfpr": "ENTERPRISE_CF_AI_AGENT",
        "revs": "REVENUE_STANDARD",
        "revp": "REVENUE_INTERMEDIATE",
        "revpr": "REVENUE_ADVANCE",
        "capexs": "CAPEX_STANDARD",
        "capexp": "CAPEX_PLUS",
        "capexpr": "CAPEX_PREMIUM",
        "fxs": "FX_STANDARD",
        "fxp": "FX_PLUS",
        "fxpr": "FX_PREMIUM",
        "costs": "COST_STANDARD",
        "costp": "COST_PLUS",
        "costpr": "COST_PREMIUM",
        "buds": "BUDGET_STANDARD",
        "budp": "BUDGET_PLUS",
        "budpr": "BUDGET_PREMIUM",
        "reps": "REPORT_STANDARD",
        "repp": "REPORT_PLUS",
        "reppr": "REPORT_PREMIUM",
        "vars": "VARIANCE_STANDARD",
        "varp": "VARIANCE_PLUS",
        "varpr": "VARIANCE_PREMIUM",
        "mars": "MARGIN_STANDARD",
        "marp": "MARGIN_PLUS",
        "marpr": "MARGIN_PREMIUM",
        "fors": "FORECAST_STANDARD",
        "forp": "FORECAST_PLUS",
        "forpr": "FORECAST_PREMIUM",
        "decs": "DECISION_STANDARD",
        "decp": "DECISION_PLUS",
        "decpr": "DECISION_PREMIUM",
        # enterprise license (by domain)
        "en_standard": "ENTERPRISE_LICENSE_STANDARD",
        "en_professional": "ENTERPRISE_LICENSE_PRO",
        "en_unlimited": "ENTERPRISE_LICENSE_UNLIMITED",
    }

# ทำ inverse map: slug -> {skus...} (รองรับ module-0-*, *_gemini, *_ms)
_AGENT2SKUS: Dict[str, set] = {}
for sku, slug in (_SKU2SLUG or {}).items():
    s = sku.lower()
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
    """
    ทำให้ชื่อแพลตฟอร์มสม่ำเสมอ:
    - "Copilot-Enterprise" → "Copilot"
    - ค่าว่าง → "GPT" (ตั้ง default)
    """
    s = (p or "").strip()
    if s.startswith("Copilot"):
        return "Copilot"
    return s or "GPT"

def _platform_match(request_platform: str, row_platform: Optional[str]) -> bool:
    return _normalize_platform(request_platform) == _normalize_platform(row_platform)

def _tier_from_slug(agent_slug: str) -> str:
    """
    Map slug → tier ที่ต้องใช้:
    *_STANDARD / (default)   -> STANDARD
    *_PLUS / *_INTERMEDIATE  -> PLUS
    *_PREMIUM / *_ADVANCE    -> PREMIUM
    """
    s = (agent_slug or "").upper()
    if s.endswith("_PREMIUM") or s.endswith("_ADVANCE"):
        return "PREMIUM"
    if s.endswith("_PLUS") or s.endswith("_INTERMEDIATE"):
        return "PLUS"
    return "STANDARD"

_TIER_ORDER = {"STANDARD": 0, "PLUS": 1, "PREMIUM": 2}

def _tier_allows(owned: str, required: str) -> bool:
    return _TIER_ORDER.get((owned or "").upper(), -1) >= _TIER_ORDER.get((required or "").upper(), 0)

def _best_owned_tier(rows: List[Dict[str, Any]], platform: str) -> Optional[str]:
    """
    หา tier สูงสุดของผู้ใช้บนแพลตฟอร์มที่ระบุ จากตาราง tier_subscriptions
    รองรับคีย์หลายรูปแบบ: 'tier', 'tier_code', หรือ 'sku' (เช่น PLUS)
    """
    best_tier = None
    best_rank = -1
    for r in rows or []:
        if r.get("status", "active") != "active":
            continue
        if not _platform_match(platform, r.get("platform")):
            continue
        raw = (r.get("tier") or r.get("tier_code") or r.get("sku") or "").upper()
        if raw.startswith("TIER_"):
            raw = raw[5:]
        rank = _TIER_ORDER.get(raw, -1)
        if rank > best_rank:
            best_rank = rank
            best_tier = raw
    return best_tier

def _agent_skus_for_slug(agent_slug: str) -> List[str]:
    """
    คืนชุด sku ที่ถือว่าเป็น agent เดียวกับ slug นี้ (รวม alias พวก *_gemini, *_ms)
    ถ้าไม่มีในตาราง จะคืน [] เพื่อให้ตรวจแบบ row['agent_slug'] ตรงตัวแทน
    """
    return sorted(list(_AGENT2SKUS.get(agent_slug, set())))

# ---------- main gate ----------
def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    คืน True ถ้าผู้ใช้มีสิทธิ์เรียก agent_slug บน platform ที่ระบุ

    ลำดับพิจารณา (รองรับทุกแพลตฟอร์ม รวม Copilot แบบรายบุคคล):
    1) รายบุคคล - subscriptions:
       - ถ้ามี sku='all' และ platform ตรงกัน -> อนุญาตทุก agent บน platform นั้น
       - ถ้ามี row ที่ระบุ agent โดยตรง (agent_slug/agent/agent_id ตรง) -> อนุญาตเฉพาะเอเจนต์นั้น
       - ถ้ามี sku ที่ match กับ agent_slug (จากตาราง map) + platform ตรง -> อนุญาตเอเจนต์นั้น
    2) รายบุคคล - tier_subscriptions:
       - STANDARD อนุญาตเฉพาะเอเจนต์ที่ต้องการ STANDARD
       - PLUS     อนุญาต STANDARD + PLUS
       - PREMIUM  อนุญาตทั้งหมด
       (ใช้กับ GPT/Gemini/Copilot ได้เท่าเทียมกัน โดยดู platform ตรงกัน)
    3) Enterprise (โดเมน) - เฉพาะ Copilot:
       - en_standard      -> เฉพาะเอเจนต์ที่ต้องการ STANDARD
       - en_professional  -> ทุก tier
       - en_unlimited     -> ทุก tier
    """
    platform = _normalize_platform(platform)

    # --- 1) รายบุคคล: subscriptions ---
    try:
        subs = db.fetch_subscriptions(user_email) or []
    except Exception:
        subs = []

    agent_required_tier = _tier_from_slug(agent_slug)
    skus_for_agent = set(_agent_skus_for_slug(agent_slug))

    for r in subs:
        if r.get("status", "active") != "active":
            continue
        if not _platform_match(platform, r.get("platform")):
            continue

        sku = (r.get("sku") or "").lower()
        if sku == "all":
            return True  # ทั้ง platform

        # ผูก agent รายตัวด้วย slug โดยตรง ถ้าตารางมีเก็บไว้
        row_agent_slug = r.get("agent_slug") or r.get("agent") or r.get("agent_id")
        if row_agent_slug and str(row_agent_slug).upper() == agent_slug.upper():
            return True

        # หรือผูกด้วย sku ของ agent (จากตาราง map)
        if sku and (sku in skus_for_agent or sku.replace("module-0-", "") in skus_for_agent):
            return True

    # --- 2) รายบุคคล: tier_subscriptions ---
    try:
        tier_rows = db.fetch_tier_subscriptions(user_email) or []
    except Exception:
        tier_rows = []

    owned_tier = _best_owned_tier(tier_rows, platform)  # เช่น 'PLUS'
    if owned_tier and _tier_allows(owned_tier, agent_required_tier):
        return True

    # --- 3) Enterprise license (เฉพาะ Copilot) ---
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

    # ไม่ผ่านเงื่อนไขใด ๆ
    return False
