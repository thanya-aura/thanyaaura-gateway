# app/main.py — safe version with /health, /routes, and /billing/thrivecart

import re
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request

# try import helper; ถ้าไม่มีให้ fallback
try:
    from app.agents import (
        get_agent_slug_from_sku,  # ฟังก์ชันที่ตัด module-0-
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
    คืน slug แบบสั้น เช่น 'project_cf':
    - ถ้ามี sku/passthrough[sku] ใช้นั้น (ตัด module-0- ถ้ามี)
    - ไม่งั้นเดาจาก fulfillment[url]
    """
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        s = sku.strip().lower()
        if s.startswith("module-0-"):
            s = s[9:]
        return s

    f_url = data.get("fulfillment[url]") or data.get("fulfillment") or data.get("fulfillment_url")
    if f_url:
        path = urlparse(f_url).path.lower()
        m = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
        if m:
            return m.group(1)
    return None

def _fallback_get_agent_slug_from_sku(sku: str):
    """
    ใช้เมื่อไม่มี get_agent_slug_from_sku ใน agents:
    - normalize เป็นคีย์สั้น
    - lookup ทั้งแบบสั้นและแบบมี prefix เผื่อ dict เก่า
    - ถ้าได้ CODE → map เป็น agent_slug ด้วย AGENT_CODE_TO_SLUG
    """
    s = (sku or "").strip().lower()
    if s.startswith("module-0-"):
        s = s[9:]
    val = AGENT_SKU_TO_CODE.get(s) or AGENT_SKU_TO_CODE.get(f"module-0-{s}")
    if val is None:
        return None
    if isinstance(val, str) and "_" in val:
        return val
    return AGENT_CODE_TO_SLUG.get(val)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/routes")
async def routes():
    return [r.path for r in app.routes]

@app.post("/billing/thrivecart")
async def billing_thrivecart(request: Request):
    # ThriveCart ส่งเป็น form-urlencoded
    form = await request.form()
    data = dict(form)

    # TODO: ตรวจ secret ถ้าคุณเปิดไว้
    # secret = data.get("thrivecart_secret") or request.headers.get("X-THRIVECART-SECRET")
    # if secret != os.environ.get("THRIVECART_SECRET"): raise HTTPException(401, "Unauthorized")

    sku = derive_sku(data)
    if not sku:
        raise HTTPException(400, "Missing SKU (or fulfillment[url])")

    if callable(get_agent_slug_from_sku):
        agent_slug = get_agent_slug_from_sku(sku)
    else:
        agent_slug = _fallback_get_agent_slug_from_sku(sku)

    if not agent_slug:
        raise HTTPException(400, f"Unknown SKU: {sku}")

    # TODO: your original logic to upsert subscriptions + grant entitlements
    return {"ok": True, "sku": sku, "agent_slug": agent_slug}

