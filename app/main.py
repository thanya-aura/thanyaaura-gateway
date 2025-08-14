# app/main.py — FastAPI with /health, /routes, /debug/* และ /billing/thrivecart
# ใช้ get_agent_slug_from_sku() จาก app.agents และรองรับทั้ง form & JSON

import os
import re
import json
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request

# import แบบปลอดภัย (เผื่อ agents.py ยังไม่อัปเดต)
try:
    from app.agents import get_agent_slug_from_sku, AGENT_SKU_TO_AGENT
except Exception:  # pragma: no cover
    get_agent_slug_from_sku = None
    AGENT_SKU_TO_AGENT = {}

app = FastAPI(title="Thanyaaura Gateway", version="1.0.0")

def _drop_module_prefix(s: str) -> str:
    s = (s or "").strip().lower()
    if s.startswith("module-0-"):
        s = s[9:]
    return s

def derive_sku_from_url(url_str: str | None) -> str | None:
    """
    พยายามดึง slug จาก fulfillment URL เช่น /module-0-cfp/confirm/...
    คืนค่าเป็น slug แบบสั้น ('cfp', 'revenue_standard')
    """
    if not url_str:
        return None
    try:
        path = urlparse(url_str).path.lower()
        m = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

def derive_sku(data: dict) -> str | None:
    """
    ลำดับความสำคัญ:
      1) 'sku' หรือ 'passthrough[sku]' (ตัด module-0- ถ้ามี)
      2) fulfillment[url] / fulfillment / fulfillment_url (ตัดจาก path)
    """
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        return _drop_module_prefix(sku)

    f_url = (
        data.get("fulfillment[url]") or
        data.get("fulfillment_url") or
        data.get("fulfillment")
    )
    return derive_sku_from_url(f_url)

async def read_payload(request: Request) -> dict:
    """
    รับทั้ง application/x-www-form-urlencoded และ application/json
    คืน dict ที่รวม field สำคัญ
    """
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            body = await request.body()
            return json.loads(body.decode("utf-8") or "{}")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    else:
        form = await request.form()
        return dict(form)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/routes")
async def routes():
    return [r.path for r in app.routes]

@app.get("/debug/resolve")
async def debug_resolve(sku: str):
    """
    ทดสอบ map SKU -> agent_slug อย่างเร็ว:
      - ยอมรับ 'cfp' / 'module-0-cfp' / 'project_cf' ฯลฯ
    """
    if callable(get_agent_slug_from_sku):
        agent = get_agent_slug_from_sku(sku)
    else:
        agent = None
    return {"sku_in": sku, "agent_slug": agent}

@app.get("/debug/sku-keys")
async def debug_sku_keys():
    """ดูคีย์ทั้งหมดที่ตัวแมปปัจจุบันรู้จัก (มีทั้ง canonical และ alias)"""
    try:
        return sorted(AGENT_SKU_TO_AGENT.keys())
    except Exception:
        return []

@app.post("/billing/thrivecart")
async def billing_thrivecart(request: Request):
    """
    ThriveCart webhook endpoint
    (ค่าเริ่มต้น ThriveCart ส่งเป็น application/x-www-form-urlencoded)
    """
    data = await read_payload(request)

    # ถ้าต้องบังคับเช็ค secret ให้ uncomment 4 บรรทัดด้านล่าง:
    # secret_in = data.get("thrivecart_secret") or request.headers.get("X-THRIVECART-SECRET")
    # secret_env = os.environ.get("THRIVECART_SECRET")
    # if not secret_in or not secret_env or secret_in != secret_env:
    #     raise HTTPException(status_code=401, detail="Unauthorized")

    # สกัด sku ให้เป็นรูปแบบสั้น
    sku = derive_sku(data)
    if not sku:
        raise HTTPException(status_code=400, detail="Missing SKU (or fulfillment[url])")

    # map เป็น agent_slug ด้วยตัว resolver กลางจาก agents.py
    if not callable(get_agent_slug_from_sku):
        raise HTTPException(status_code=500, detail="Resolver not available")

    agent_slug = get_agent_slug_from_sku(sku)
    if not agent_slug:
        # ช่วย debug โดยบอกคีย์บางส่วนที่รู้จัก
        known = list(AGENT_SKU_TO_AGENT.keys())[:12]
        raise HTTPException(status_code=400, detail=f"Unknown SKU: {sku}. Try one of: {known} ...")

    # TODO: ที่นี่ใส่ logic เดิมของคุณ เช่น:
    # - upsert into subscriptions (id, user_email, sku, status)
    # - grant entitlements หรือปล่อยให้ effective_agents รวมสิทธิ์จาก tier
    # หมายเหตุ: ให้เก็บ sku ที่สั้น (เช่น 'cfp') เพื่อความสม่ำเสมอ

    return {
        "ok": True,
        "sku": sku,
        "agent_slug": agent_slug,
        # debug fields (ลบออกได้ภายหลัง)
        "event": data.get("event"),
        "order_id": data.get("order_id") or data.get("invoice_id"),
        "email": data.get("customer[email]") or data.get("email"),
    }
