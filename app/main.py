from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from app.runner import AgentRunner

app = FastAPI(title="Thanayaura Dual-Provider Gateway", version="2.1.0")
runner = AgentRunner()

# Enable CORS (temporary allow all, change in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role in conversation: system, user, assistant")
    content: str = Field(..., description="Content of the message")

class RunReq(BaseModel):
    agent_slug: str
    provider: Optional[str] = None
    model: Optional[str] = None
    input: Dict[str, Any] = Field(default_factory=dict)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/v1/agents")
def list_agents():
    from app.agents import AGENT_SPECS
    return {"ok": True, "agents": list(AGENT_SPECS.keys())}

@app.post("/v1/run")
async def run(req: RunReq, request: Request):
    trace_id = str(uuid.uuid4())
    try:
        messages = req.input.get("messages", [])
        if not isinstance(messages, list):
            raise HTTPException(400, "input.messages must be a list")
        result = await runner.run(req.agent_slug, req.provider, messages, req.model)
        return {"ok": True, "trace_id": trace_id, "result": result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Internal error: {e}")


import os
from fastapi import FastAPI

app = FastAPI()

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

# สมมติว่าก่อนหน้านี้มีบรรทัด: app = FastAPI()

@app.get("/", include_in_schema=False)
def root():
    # จะเลือก redirect ไป /docs หรือส่ง JSON ก็ได้
    return RedirectResponse(url="/docs")
    # หรือใช้แบบ JSON:
    # return {"ok": True, "service": "thanyaaura-gateway"}

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

# app/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os, logging

# มีอยู่แล้ว:
# app = FastAPI()

@app.post("/billing/thrivecart")
async def thrivecart_webhook(request: Request):
    # รองรับทั้ง form-urlencoded (ค่า default ของ ThriveCart) และ JSON
    content_type = (request.headers.get("content-type") or "").lower()
    data = {}
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        data = dict(form)
    else:
        try:
            data = await request.json()
        except Exception:
            data = {}

    # ตรวจ secret word ตามคู่มือ ThriveCart (field: thrivecart_secret)
    expected = os.getenv("THRIVECART_SECRET", "")
    provided = (data.get("thrivecart_secret") or "").strip()

    if not expected:
        raise HTTPException(status_code=500, detail="server secret missing")
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid secret")

    # ดึงข้อมูลหลัก (ปรับได้ตามจริง)
    email = data.get("customer[email]") or data.get("customer_email") or data.get("email")
    event = data.get("event")  # เช่น order.success, order.subscription_cancelled
    sku   = data.get("sku")    # ถ้าคุณส่ง sku มาด้วย

    logging.getLogger("thrivecart").info(f"TC webhook ok: event=%s email=%s sku=%s", event, email, sku)

    # TODO: ใส่โค้ด UPSERT ลง DB (users/subscriptions/agent_entitlements) ตรงนี้เมื่อพร้อม
    return {"ok": True}

from fastapi import FastAPI, Request, HTTPException, Response
# app = FastAPI()  # มีอยู่แล้ว

@app.head("/billing/thrivecart", include_in_schema=False)
def thrivecart_head():
    # ให้ ThriveCart เช็ก HEAD แล้วได้ 200
    return Response(status_code=200)

@app.get("/billing/thrivecart", include_in_schema=False)
def thrivecart_get():
    # เปิด GET ให้ 200 เฉยๆ (ไม่เปิดข้อมูลใดๆ)
    return {"ok": True}

import os, logging
from datetime import datetime
import psycopg  # psycopg3

DB_URL = os.getenv("DATABASE_URL")

def tc_event_to_status(event: str) -> str:
    m = {
        "order.success": "active",
        "order.subscription_payment": "active",
        "order.subscription_resumed": "resumed",
        "order.subscription_paused": "paused",
        "order.subscription_cancelled": "cancelled",
        "order.refund": "refunded",
        "order.rebill_failed": "past_due",
    }
    return m.get((event or "").strip(), "active")

def parse_expires_at(data: dict):
    iso = (
        data.get("next_payment_date")
        or data.get("subscription[next_payment_date]")
        or data.get("next_payment_due")
    )
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None

def upsert_from_tc(data: dict):
    """
    UPSERT:
      - users(email)
      - subscriptions(id, user_email, sku, status, expires_at)
      - agent_entitlements (จาก tier_agents หรือ product_agents ตามชนิด SKU)
    """
    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set")

    email = (data.get("customer[email]") or data.get("customer_email") or data.get("email") or "").lower()
    # ใส่ sku ลงใน ThriveCart ผ่าน passthrough จะดีที่สุด (ให้ตรง products.sku)
    sku   = data.get("sku") or data.get("product_sku") or data.get("passthrough_sku")
    sub_id = (data.get("subscription_id")
              or data.get("subscription[id]")
              or data.get("order_id")  # fallback
              or data.get("invoice_id"))
    status = tc_event_to_status(data.get("event"))
    expires_at = parse_expires_at(data)

    if not email or not sku or not sub_id:
        raise ValueError("missing required fields (email/sku/sub_id)")

    with psycopg.connect(DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # users
            cur.execute(
                "insert into users(email) values (%s) on conflict (email) do nothing;",
                (email,)
            )
            # subscriptions
            cur.execute("""
                insert into subscriptions(id, user_email, sku, status, expires_at)
                values (%s, %s, %s, %s, %s)
                on conflict (id) do update set
                  user_email = excluded.user_email,
                  sku        = excluded.sku,
                  status     = excluded.status,
                  expires_at = excluded.expires_at;
            """, (str(sub_id), email, sku, status, expires_at))

            # grant agents (ดูจากชนิด SKU ใน products):
            cur.execute("""
                with src as (
                  -- กรณีเป็น 'tier' ให้แตกสิทธิ์จาก tier_agents
                  select ta.agent_slug, %s::timestamptz as expires_at
                  from products p
                  join tier_agents ta on ta.tier_sku = p.sku
                  where p.sku = %s and p.kind = 'tier'
                  union
                  -- กรณีเป็น 'agent' ให้ map จาก product_agents
                  select pa.agent_slug, %s::timestamptz as expires_at
                  from products p
                  join product_agents pa on pa.sku = p.sku
                  where p.sku = %s and p.kind = 'agent'
                )
                insert into agent_entitlements(user_email, agent_slug, expires_at, source_subscription_id)
                select %s, agent_slug, expires_at, %s
                from src
                on conflict (user_email, agent_slug)
                do update set
                  expires_at = excluded.expires_at,
                  source_subscription_id = excluded.source_subscription_id;
            """, (expires_at, sku, expires_at, sku, email, str(sub_id)))

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from urllib.parse import parse_qs

app = FastAPI()

@app.head("/billing/thrivecart", include_in_schema=False)
def thrivecart_head():
    return Response(status_code=200)

@app.get("/billing/thrivecart", include_in_schema=False)
def thrivecart_get():
    return {"ok": True}

@app.post("/billing/thrivecart")
async def thrivecart_webhook(request: Request):
    # parse body (form urlencoded เป็นค่า default ของ ThriveCart)
    ctype = (request.headers.get("content-type") or "").lower()
    data = {}
    if "application/json" in ctype:
        data = await request.json()
    else:
        # พยายามอ่าน form — ถ้าไม่มี python-multipart จะ fallback ไป parse_qs
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            raw = await request.body()
            parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            data = {k: (v[0] if isinstance(v, list) and v else v) for k, v in parsed.items()}

    # ตรวจ secret word (global: ThriveCart order validation)
    expected = (os.getenv("THRIVECART_SECRET") or "").strip()
    provided = (data.get("thrivecart_secret") or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="server secret missing")
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid secret")

    # UPSERT ลงฐานข้อมูล
    try:
        upsert_from_tc(data)
    except Exception as e:
        logging.exception("UPSERT failed")
        raise HTTPException(status_code=500, detail="upsert_failed")

    return {"ok": True}
