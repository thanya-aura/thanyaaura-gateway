# app/enterprise_access.py
import os
import re
from typing import Optional

from app import db  # ใช้ fast-path เดิมของคุณ
import psycopg      # เพิ่ม fallback DB ตรวจสิทธิ์ตรง

# คงของเดิม
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
    # ถ้า request_platform ว่าง ให้ถือเป็น wildcard (ใช้กับ fallback query)
    return (rp == "" or rp == lp)

# ------------------------------
# Fallback DB helpers (ใหม่)
# ------------------------------
def _db_url() -> Optional[str]:
    return os.getenv("DATABASE_URL") or os.getenv("DB_URL")

def _connect():
    url = _db_url()
    if not url:
        return None
    try:
        return psycopg.connect(url, autocommit=True)
    except Exception:
        return None

def _exists(cur, sql: str, params: tuple) -> bool:
    cur.execute(sql, params)
    return cur.fetchone() is not None

def _has_agent_entitlement_email(email: str, agent_slug_or_sku: str, platform: str) -> bool:
    """
    ตรวจในตาราง entitlements (email-level)
    - พยายามเช็ค agent_slug ก่อน ถ้า schema ใช้ sku ก็เช็คซ้ำให้
    """
    conn = _connect()
    if not conn:
        return False
    try:
        with conn, conn.cursor() as cur:
            # agent_slug
            try:
                if _exists(
                    cur,
                    """
                    SELECT 1 FROM entitlements
                    WHERE LOWER(email)=LOWER(%s)
                      AND LOWER(agent_slug)=LOWER(%s)
                      AND LOWER(platform)=LOWER(%s)
                    LIMIT 1
                    """,
                    (email, agent_slug_or_sku, platform),
                ):
                    return True
            except Exception:
                pass

            # sku
            try:
                if _exists(
                    cur,
                    """
                    SELECT 1 FROM entitlements
                    WHERE LOWER(email)=LOWER(%s)
                      AND LOWER(sku)=LOWER(%s)
                      AND LOWER(platform)=LOWER(%s)
                    LIMIT 1
                    """,
                    (email, agent_slug_or_sku, platform),
                ):
                    return True
            except Exception:
                pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return False

def _has_any_tier_for_platform(email: str, platform: str) -> bool:
    """
    ตรวจในตาราง tier_subscriptions ว่ามี record สำหรับ email+platform ไหม
    (ระหว่างทดสอบ อนุญาตทุก agent หากมี tier ใด ๆ บน platform นั้น)
    """
    conn = _connect()
    if not conn:
        return False
    try:
        with conn, conn.cursor() as cur:
            try:
                return _exists(
                    cur,
                    """
                    SELECT 1 FROM tier_subscriptions
                    WHERE LOWER(email)=LOWER(%s)
                      AND LOWER(platform)=LOWER(%s)
                    LIMIT 1
                    """,
                    (email, platform),
                )
            except Exception:
                return False
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _has_enterprise_email(email: str, platform: str) -> bool:
    """
    ตรวจในตาราง enterprise_licenses ที่ผูกกับ email โดยตรง
    """
    conn = _connect()
    if not conn:
        return False
    try:
        with conn, conn.cursor() as cur:
            try:
                return _exists(
                    cur,
                    """
                    SELECT 1 FROM enterprise_licenses
                    WHERE LOWER(email)=LOWER(%s)
                      AND LOWER(platform)=LOWER(%s)
                    LIMIT 1
                    """,
                    (email, platform),
                )
            except Exception:
                return False
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ------------------------------
# Main checker
# ------------------------------
def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    คืน True ถ้า user มีสิทธิ์เรียก agent_slug บน platform ที่ระบุ

    ลำดับกติกา (รวม fast-path เดิม + fallback DB):
    1) สิทธิ์รายบุคคล (fast-path: db.fetch_subscriptions)
       - ถ้ามีแถว sku='all' บน platform เดียวกัน -> ผ่าน
       - (สามารถต่อยอด map agent_slug -> sku แล้วเทียบราย agent ได้ในอนาคต)
    2) Fallback email-level:
       - entitlements(email, agent_slug/sku, platform) -> ผ่าน
       - tier_subscriptions(email, platform)           -> ผ่าน (อนุญาตทุก agent ชั่วคราว)
       - enterprise_licenses(email, platform)          -> ผ่าน
    3) สิทธิ์ enterprise แบบโดเมน (เดิม):
       - ใช้ได้เฉพาะ Copilot (รวม Copilot-Enterprise)
       - en_standard      -> เรียกได้เฉพาะเอเจนต์ tier STANDARD
       - en_professional  -> เรียกได้ทุก tier
       - en_unlimited     -> เรียกได้ทุก tier
    """
    # ---------- 1) fast-path บนตาราง subscriptions ของผู้ใช้ ----------
    try:
        rows = db.fetch_subscriptions(user_email) or []
        rows = [r for r in rows if (r.get("status") == "active")]
        for r in rows:
            if r.get("sku") == "all" and _platform_match(platform, r.get("platform") or ""):
                return True
        # NOTE: ถ้าต้องการเช็ค per-agent report จาก subscriptions เพิ่ม:
        # - ทำ mapping agent_slug -> sku แล้วเช็ค r["sku"] == mapped_sku และ platform ตรงกัน
    except Exception:
        # ถ้า fast-path error ให้ไป fallback ต่อ
        pass

    # ---------- 2) fallback email-level (ตาราง entitlements / tier_subscriptions / enterprise_licenses) ----------
    # 2.1 agent-level entitlements (email)
    try:
        if _has_agent_entitlement_email(user_email, agent_slug, platform):
            return True
    except Exception:
        pass

    # 2.2 tier subscriptions (email) — อนุญาตทุก agent หากพบ tier บน platform เดียวกัน
    try:
        if _has_any_tier_for_platform(user_email, platform):
            return True
    except Exception:
        pass

    # 2.3 enterprise licenses (email)
    try:
        if _has_enterprise_email(user_email, platform):
            return True
    except Exception:
        pass

    # ---------- 3) enterprise domain license (เดิม) เฉพาะ Copilot* ----------
    if not (platform or "").startswith("Copilot"):
        return False

    domain = _email_domain(user_email)
    if not domain:
        return False

    try:
        ent = db.get_active_enterprise_license_for_domain(domain)
    except Exception:
        ent = None

    if not ent:
        return False  # ไม่มี license active ของโดเมนนี้

    if not _platform_match(platform, ent.get("platform") or ""):
        return False

    lic = (ent.get("sku") or "").lower()
    agent_tier = _tier_from_slug(agent_slug) or "STANDARD"  # default ให้ปลอดภัยสุด

    if lic == "en_standard":
        return agent_tier == "STANDARD"
    if lic in ("en_professional", "en_unlimited"):
        return True

    return False
