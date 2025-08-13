# app/main.py
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid
import os, logging
from urllib.parse import parse_qs
from datetime import datetime
import psycopg  # psycopg3

# ---- App & Logging ----
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("thanyaaura-gateway")

app = FastAPI(title="Thanyaaura Gateway", version="2.2.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Models ----
class ChatMessage(BaseModel):
    role: str = Field(...)
    content: str = Field(...)

class RunReq(BaseModel):
    agent_slug: str
    provider: Optional[str] = None
    model: Optional[str] = None
    input: Dict[str, Any] = Field(default_factory=dict)

# ---- Agents Runner endpoints ----
try:
    from app.runner import AgentRunner
    runner = AgentRunner()
except Exception as e:
    logging.getLogger("runner").warning("AgentRunner not available: %s", e)
    runner = None

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

@app.get("/v1/agents")
def list_agents():
    try:
        from app.agents import AGENT_SPECS
        return {"ok": True, "agents": list(AGENT_SPECS.keys())}
    except Exception as e:
        raise HTTPException(500, f"AGENT_SPECS unavailable: {e}")

@app.post("/v1/run")
async def run(req: RunReq, request: Request):
    trace_id = str(uuid.uuid4())
    if runner is None:
        raise HTTPException(500, "AgentRunner not initialized")
    try:
        messages = req.input.get("messages", [])
        if not isinstance(messages, list):
            raise HTTPException(400, "input.messages must be a list")
        result = await runner.run(req.agent_slug, req.provider, messages, req.model)
        return {"ok": True, "trace_id": trace_id, "result": result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Run failed")
        raise HTTPException(500, f"Internal error: {e}")

# ---- DB helpers (ThriveCart) ----
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
    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set")

    email = (data.get("customer[email]") or data.get("customer_email") or data.get("email") or "").lower()
    sku   = data.get("sku") or data.get("product_sku") or data.get("passthrough_sku")
    sub_id = (data.get("subscription_id")
              or data.get("subscription[id]")
              or data.get("order_id")
              or data.get("invoice_id"))
    status = tc_event_to_status(data.get("event"))
    expires_at = parse_expires_at(data)

    if not email or not sku or not sub_id:
        raise ValueError("missing required fields (email/sku/sub_id)")

    with psycopg.connect(DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into users(email) values (%s) on conflict (email) do nothing;",
                (email,)
            )
            cur.execute(
                '''
                insert into subscriptions(id, user_email, sku, status, expires_at)
                values (%s, %s, %s, %s, %s)
                on conflict (id) do update set
                  user_email = excluded.user_email,
                  sku        = excluded.sku,
                  status     = excluded.status,
                  expires_at = excluded.expires_at;
                ''',
                (str(sub_id), email, sku, status, expires_at)
            )
            cur.execute(
                '''
                with src as (
                  select ta.agent_slug, %s::timestamptz as expires_at
                  from products p
                  join tier_agents ta on ta.tier_sku = p.sku
                  where p.sku = %s and p.kind = 'tier'
                  union
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
                ''',
                (expires_at, sku, expires_at, sku, email, str(sub_id))
            )

# ---- ThriveCart webhook endpoints ----
@app.head("/billing/thrivecart", include_in_schema=False)
def thrivecart_head():
    return Response(status_code=200)

@app.get("/billing/thrivecart", include_in_schema=False)
def thrivecart_get():
    return {"ok": True}

@app.post("/billing/thrivecart")
async def thrivecart_webhook(request: Request):
    ctype = (request.headers.get("content-type") or "").lower()
    data = {}
    if "application/json" in ctype:
        data = await request.json()
    else:
        try:
            form = await request.form()  # needs python-multipart
            data = dict(form)
        except Exception:
            raw = await request.body()
            parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            data = {k: (v[0] if isinstance(v, list) and v else v) for k, v in parsed.items()}

    expected = (os.getenv("THRIVECART_SECRET") or "").strip()
    provided = (data.get("thrivecart_secret") or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="server secret missing")
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid secret")

    try:
        upsert_from_tc(data)
    except Exception:
        logging.exception("UPSERT failed")
        raise HTTPException(status_code=500, detail="upsert_failed")

    logger.info("TC webhook OK: event=%s email=%s sku=%s",
                data.get("event"),
                data.get("customer[email]") or data.get("customer_email") or data.get("email"),
                data.get("sku"))
    return {"ok": True}
