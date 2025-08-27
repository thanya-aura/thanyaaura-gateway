# app/enterprise_access.py
import re
from typing import Optional
from app import db

ENTERPRISE_SKUS = {"en_standard", "en_professional", "en_unlimited"}

def _email_domain(email: str) -> Optional[str]:
    try:
        return email.split("@", 1)[1].lower()
    except Exception:
        return None

def _tier_from_slug(agent_slug: str) -> Optional[str]:
    """
    แยกระดับเอเจนต์จาก slug ภายในระบบ เช่น:
    - *_STANDARD      -> STANDARD
    - *_PLUS          -> PLUS
    - *_INTERMEDIATE  -> PLUS   (map มาที่ PLUS)
    - *_PREMIUM       -> PREMIUM
    - *_ADVANCE       -> PREMIUM (map)
    """
    s = (agent_slug or "").upper()
    if s.endswith("_STANDARD"):
        return "STANDARD"
    if s.endswith("_PLUS") or s.endswith("_INTERMEDIATE"):
        return "PLUS"
    if s.endswith("_PREMIUM") or s.endswith("_ADVANCE"):
        return "PREMIUM"
    return None

def _platform_match(request_platform: str, row_platform: str) -> bool:
    """
    Copilot-Enterprise นับเป็น Copilot ด้วย
    """
    rp = (request_platform or "").strip()
    rp = "Copilot" if rp.startswith("Copilot") else rp
    lp = (row_platform or "").strip()
    lp = "Copilot" if lp.startswith("Copilot") else lp
    return (rp == "" or rp == lp)

def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    คืน True ถ้า user มีสิทธิ์เรียก agent_slug บน platform ที่ระบุ
    กติกา:
    - สิทธิ์รายบุคคล:
        * ถ้ามีแถว sku='all' บน platform เดียวกัน -> ผ่าน
        * (ถ้าต้องการเช็ค per-agent ให้ map slug -> sku แล้วเทียบกับ subscriptions ของ user)
    - สิทธิ์ enterprise (โดเมน):
        * ใช้ได้เฉพาะ Copilot (รวม Copilot-Enterprise)
        * en_standard      -> เรียกได้เฉพาะเอเจนต์ tier STANDARD
        * en_professional  -> เรียกได้ทุก tier
        * en_unlimited     -> เรียกได้ทุก tier
    - ถ้าสถานะโดเมนถูกยกเลิก (ไม่มี row active) -> ปฏิเสธ
    """
    # 1) เช็คสิทธิ์รายบุคคลจาก subscriptions ของ user ก่อน
    rows = db.fetch_subscriptions(user_email) or []
    rows = [r for r in rows if r.get("status") == "active"]
    # 'all' บน platform เดียวกัน => ผ่านทันที
    for r in rows:
        if r.get("sku") == "all" and _platform_match(platform, r.get("platform")):
            return True

    # (ถ้าต้องการเช็ค per-agent รายตัวแบบบุคคล:
    #  แปลง agent_slug -> sku ตระกูลนั้น แล้วเทียบ r["sku"] == <sku> และ platform ตรงกัน)

    # 2) เช็คสิทธิ์ enterprise domain เฉพาะ Copilot เท่านั้น
    if not (platform or "").startswith("Copilot"):
        return False

    domain = _email_domain(user_email)
    if not domain:
        return False

    ent = db.get_active_enterprise_license_for_domain(domain)
    if not ent:
        return False  # ไม่มี license active ของโดเมนนี้

    if not _platform_match(platform, ent.get("platform")):
        return False

    lic = (ent.get("sku") or "").lower()
    agent_tier = _tier_from_slug(agent_slug) or "STANDARD"  # default ให้ปลอดภัยสุด

    if lic == "en_standard":
        return agent_tier == "STANDARD"
    if lic in ("en_professional", "en_unlimited"):
        return True

    return False
