# app/enterprise_access.py
from typing import Optional, Dict, Any, Tuple
from app import db

TIER_SKUS = {"standard", "plus", "premium"}
ENTERPRISE_SKUS = {"en_standard", "en_professional", "en_unlimited"}

# map จาก agent_slug/alisa -> base sku (เพื่อผูก agent-level ให้ตรง)
AGENT_SLUG_TO_BASE = {
    # cashflow family
    "SINGLE_CF_AI_AGENT": "cfs",
    "PROJECT_CF_AI_AGENT": "cfp",
    "ENTERPRISE_CF_AI_AGENT": "cfpr",
    # เผื่อมีการส่งมาเป็น alias name
    "single_cf": "cfs",
    "project_cf": "cfp",
    "enterprise_cf": "cfpr",
}

# ---------- helpers ----------
def _email_domain(email: str) -> Optional[str]:
    try:
        return email.split("@", 1)[1].lower()
    except Exception:
        return None

def _tier_from_slug(agent_slug: str) -> str:
    s = (agent_slug or "").upper()
    if s.endswith("_STANDARD"):
        return "STANDARD"
    if s.endswith("_PLUS") or s.endswith("_INTERMEDIATE"):
        return "PLUS"
    if s.endswith("_PREMIUM") or s.endswith("_ADVANCE"):
        return "PREMIUM"
    return "STANDARD"  # default ปลอดภัยสุด

def _tier_allows(user_tier: str, agent_tier: str) -> bool:
    order = {"STANDARD": 1, "PLUS": 2, "PREMIUM": 3}
    return order.get((user_tier or "").upper(), 0) >= order.get((agent_tier or "").upper(), 0)

def _platform_norm(p: Optional[str]) -> str:
    """
    รวมชื่อแพลตฟอร์มให้เป็นชุดเดียว:
      - GPT
      - Gemini
      - Copilot
    รองรับ input: gpt/openai, gemini/google, ms/microsoft/copilot, ว่าง ("")
    """
    x = (p or "").strip().lower()
    if x in ("", "gpt", "openai"):
        return "GPT"
    if x in ("gemini", "google"):
        return "Gemini"
    if x in ("ms", "microsoft", "copilot"):
        return "Copilot"
    # ค่าอื่นๆ ให้คงไว้ตามเดิม (แต่ส่วนใหญ่จะไม่เข้ามาถึงตรงนี้)
    return (p or "").strip()

def _parse_base_and_suffix_platform(sku: str) -> Tuple[str, Optional[str]]:
    """
    คืน (base_sku, platform_from_suffix)
      cfs_gemini -> ("cfs", "Gemini")
      cfs_ms     -> ("cfs", "Copilot")
      cfs        -> ("cfs", None)
    """
    t = (sku or "").strip().lower()
    if t.endswith("_gemini"):
        return t[:-7], "Gemini"
    if t.endswith("_ms"):
        return t[:-3], "Copilot"
    return t, None

def _expected_base_from_agent_slug(agent_slug: str) -> str:
    a = (agent_slug or "").strip()
    return AGENT_SLUG_TO_BASE.get(a, AGENT_SLUG_TO_BASE.get(a.upper(), a.lower()))

def _platform_match(request_platform: str, row_platform: str, *, is_tier: bool) -> bool:
    """
    - สำหรับ Tier: ถ้า row platform เป็นว่าง/หรือถูก normalize เป็น GPT ให้ถือเป็น wildcard (ใช้ได้ทุกแพลตฟอร์ม)
      เพื่อแก้เคสที่ webhook persist tier เป็น GPT เสมอ
    - สำหรับ agent-level: ต้องเท่ากันตรงตัวหลัง normalize (เว้นแต่ row ระบุเป็นว่าง -> ถือว่าปริยาย GPT)
    """
    req = _platform_norm(request_platform)
    row = _platform_norm(row_platform)

    if is_tier:
        # tier ใช้ได้ทุกแพลตฟอร์ม หาก row ไม่ล็อก platform ไว้ชัดเจน (ว่าง/GPT)
        if row in ("", "GPT"):
            return True
        return req == row

    # agent-level ต้อง match ตรงแพลตฟอร์ม (ถ้า row ว่าง = GPT)
    return req == row

# ---------- main checker ----------
def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    สิทธิ์รายบุคคล:
      - ถ้ามี subscription sku='all' (any-agent) ที่ platform ตรงกัน (หรือ tier-mode wildcard) -> ผ่าน
      - ถ้ามี subscription เป็น tier (standard/plus/premium) ที่ platform ตรงกัน (tier-mode wildcard) ->
            อนุญาตตามระดับ tier (PLUS ครอบ STANDARD, PREMIUM ครอบทั้งหมด)
      - ถ้ามี subscription เป็น agent รายตัว (ไม่ใช่ tier/enterprise/all) และ platform ตรงกัน
            (พิจารณา base sku + suffix _gemini/_ms) -> ผ่าน

    สิทธิ์ enterprise (โดเมน):
      - ใช้ได้เฉพาะตระกูล Copilot (รวม Copilot-Enterprise)
      - en_standard      -> เรียกได้เฉพาะเอเจนต์ tier STANDARD
      - en_professional  -> เรียกได้ทุก tier
      - en_unlimited     -> เรียกได้ทุก tier
    """
    rows = [r for r in (db.fetch_subscriptions(user_email) or []) if r.get("status") == "active"]

    # 1) บุคคล: any-agent (sku='all')
    for r in rows:
        if (r.get("sku") or "").lower() == "all":
            if _platform_match(platform, r.get("platform"), is_tier=True):
                return True

    # 2) บุคคล: Tier บน GPT/Gemini/Copilot (tier-mode platform wildcard)
    agent_tier = _tier_from_slug(agent_slug)
    for r in rows:
        sku = (r.get("sku") or "").lower()
        if sku in TIER_SKUS:
            if _platform_match(platform, r.get("platform"), is_tier=True):
                # map "standard|plus|premium" -> ระดับ tier
                if _tier_allows(sku.upper(), agent_tier):
                    return True

    # 3) บุคคล: ซื้อรายเอเจนต์ (strict platform match + base sku ตรง agent_slug)
    expected_base = _expected_base_from_agent_slug(agent_slug)  # เช่น SINGLE_CF_AI_AGENT -> "cfs"
    for r in rows:
        sku_raw = (r.get("sku") or "").lower()
        if sku_raw in (TIER_SKUS | ENTERPRISE_SKUS | {"all"}):
            continue  # ไม่ใช่ agent-level

        row_base, sku_suffix_platform = _parse_base_and_suffix_platform(sku_raw)
        # platform ที่บันทึกมาใน row; ถ้าไม่มีให้ใช้ที่สื่อจาก suffix ของ sku
        stored_platform = r.get("platform")
        effective_row_platform = stored_platform if stored_platform else (sku_suffix_platform or "GPT")

        if row_base == expected_base and _platform_match(platform, effective_row_platform, is_tier=False):
            return True

    # 4) Enterprise (โดเมน) — เฉพาะ Copilot family
    if _platform_norm(platform) != "Copilot":
        return False

    domain = _email_domain(user_email)
    if not domain:
        return False

    ent = db.get_active_enterprise_license_for_domain(domain)
    if not ent or not _platform_match(platform, ent.get("platform"), is_tier=True):
        return False

    lic = (ent.get("sku") or "").lower()
    if lic == "en_standard":
        return agent_tier == "STANDARD"
    if lic in ("en_professional", "en_unlimited"):
        return True

    return False
