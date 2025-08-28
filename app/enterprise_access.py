# app/enterprise_access.py
from typing import Optional
from app import db

TIER_SKUS = {"standard", "plus", "premium"}
ENTERPRISE_SKUS = {"en_standard", "en_professional", "en_unlimited"}

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
    p = (p or "").strip()
    return "Copilot" if p.startswith("Copilot") else p

def _platform_match(request_platform: str, row_platform: str) -> bool:
    return _platform_norm(request_platform) in ("", _platform_norm(row_platform))

def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    สิทธิ์รายบุคคล:
      - ถ้ามี subscription sku='all' ที่ platform ตรงกัน -> ผ่าน
      - ถ้ามี subscription เป็น tier (standard/plus/premium) ที่ platform ตรงกัน ->
            อนุญาตตามระดับ tier (PLUS ครอบ STANDARD, PREMIUM ครอบทั้งหมด)
      - ถ้ามี subscription เป็น agent รายตัว (ไม่ใช่ tier/enterprise/all) และ platform ตรงกัน -> ผ่าน

    สิทธิ์ enterprise (โดเมน):
      - ใช้ได้เฉพาะตระกูล Copilot (รวม Copilot-Enterprise)
      - en_standard      -> เรียกได้เฉพาะเอเจนต์ tier STANDARD
      - en_professional  -> เรียกได้ทุก tier
      - en_unlimited     -> เรียกได้ทุก tier
    """
    rows = [r for r in (db.fetch_subscriptions(user_email) or []) if r.get("status") == "active"]

    # 1) บุคคล: any-agent บน platform เดียวกัน
    for r in rows:
        if (r.get("sku") or "").lower() == "all" and _platform_match(platform, r.get("platform")):
            return True

    # 2) บุคคล: Tier บน GPT/Gemini/Copilot (ทุก platform)
    agent_tier = _tier_from_slug(agent_slug)
    for r in rows:
        sku = (r.get("sku") or "").lower()
        if sku in TIER_SKUS and _platform_match(platform, r.get("platform")):
            if _tier_allows(sku.upper(), agent_tier):
                return True

    # 3) บุคคล: ซื้อรายเอเจนต์ (ไม่ใช่ tier/enterprise/all)
    for r in rows:
        sku = (r.get("sku") or "").lower()
        if sku not in (TIER_SKUS | ENTERPRISE_SKUS | {"all"}) and _platform_match(platform, r.get("platform")):
            return True

    # 4) Enterprise (โดเมน) — เฉพาะ Copilot family
    if _platform_norm(platform) != "Copilot":
        return False

    domain = _email_domain(user_email)
    if not domain:
        return False

    ent = db.get_active_enterprise_license_for_domain(domain)
    if not ent or not _platform_match(platform, ent.get("platform")):
        return False

    lic = (ent.get("sku") or "").lower()
    if lic == "en_standard":
        return agent_tier == "STANDARD"
    if lic in ("en_professional", "en_unlimited"):
        return True

    return False
