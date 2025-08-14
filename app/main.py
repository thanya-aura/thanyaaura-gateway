# app/main.py  — version with safe import + fallback for SKU mapping

import re
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request

# --- safe import with fallback ---
try:
    from app.agents import (
        get_agent_slug_from_sku,  # อาจไม่มีในรีโปเก่า จึง try/except
        AGENT_SKU_TO_CODE,
        AGENT_CODE_TO_SLUG,
    )
except Exception:
    get_agent_slug_from_sku = None
    AGENT_SKU_TO_CODE = {}
    AGENT_CODE_TO_SLUG = {}

app = FastAPI()

def derive_sku(data: dict) -> str | None:
    """
    ดึง SKU จาก body:
    1) ถ้ามี 'sku' หรือ 'passthrough[sku]' ใช้ค่านั้น
    2) ถ้าไม่มีก็เดาจาก fulfillment[url] โดยตัด 'module-0-' ออก
    คืนค่าเป็น slug แบบสั้น เช่น 'project_cf'
    """
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        s = sku.strip().lower()
        # เผื่อมีคนส่งมาเป็น module-0-...
        if s.startswith("module-0-"):
            s = s[9:]
        return s

    f_url = data.get("fulfillment[url]") or data.get("fulfillment") or data.get("fulfillment_url")
    if f_url:
        try:
            path = urlparse(f_url).path.lower()
            m = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
            if m:
                return m.group(1)  # คืน slug แบบสั้น เช่น project_cf
        except Exception:
            pass
    return None

def _fallback_get_agent_slug_from_sku(sku: str):
    """
    ใช้กรณี import get_agent_slug_from_sku ไม่สำเร็จ:
    - normalize เป็นคีย์สั้น (ตัด module-0-)
    - lookup ทั้งแบบสั้น และลองแบบมี prefix เผื่อ dict เก่า
    - ถ้าได้ CODE ให้ map กลับเป็น agent_slug ผ่าน AGENT_CODE_TO_SLUG
    - ถ้าได้ agent_slug ตรง ๆ ก็คืนเลย
    """
    s = (sku or "").strip().lower()
    if s.startswith("module-0-"):
        s = s[9:]

    val = AGENT_SKU_TO_CODE.get(s) or AGENT_SKU
