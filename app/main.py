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

