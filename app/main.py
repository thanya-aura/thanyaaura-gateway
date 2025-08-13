# app/main.py
from fastapi import FastAPI, Request, Response, HTTPException
from starlette.responses import JSONResponse
import os, re, logging
from urllib.parse import urlparse
import psycopg  # psycopg3

app = FastAPI(title="Thanyaaura Gateway", version="0.1.0")

# ---- logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("gateway")

# ---- agent mappings (optional)
try:
    from app.agents import AGENT_SKU_TO_CODE, AGENT_SLUG_TO_CODE
except Exception as e:
    AGENT_SKU_TO_CODE, AGENT_SLUG_TO_CODE = {}, {}
    logger.warning("agents mapping not loaded: %s", e)

CODE_TO_AGENT_SLUG = {code: slug for slug, code in AGENT_SLUG_TO_CODE.items()}

# ---- utils
def derive_sku(data: dict) -> str | None:
    # 1) ใช้ sku ตรง ๆ หรือ passthrough[sku]
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        return sku.strip().lower()
    # 2) เดาจาก fulfillment[url] เช่น .../module-0-cfs/confirm/...
    f_url = data.get("fulfillment[url]") or data.get("fulfillment") or data.get("fulfillment_url")
    if f_url:
        try:
            path = urlparse(f_url).path.lower()
            m = re.search(r"/(module-0-[a-z0-9]+)(?:/|$)", path)
            if m:
                return m.group(1)
        except Exception as e:
            logger.warning("parse fulfillment[url] failed: %s", e)
    return None

def upsert(db, email: str, sub_id: str, sku: str, status: str, expires_at=None, agent_slug: str | None = None):
    with db.cursor() as cur:
        cur.execute("insert into users(email) values (lower(%s)) on conflict (email) do nothing;", (email,))
        cur.execute(
            """
            insert into subscriptions(id, user_email, sku, status, expires_at)
            values (%s, lower(%s), %s, %s, %s)
            on conflict (id) do update set
              user_email = excluded.user_email,
              sku        = excluded.sku,
              status     = excluded.status,
              expires_at = excluded.expires_at
            """,
            (sub_id, email, sku, status, expires_at),
        )
        if agent_slug:
            cur.execute(
                """
                insert into agent_entitlements(user_email, agent_slug, expires_at, source_subscription_id)
                values (lower(%s), %s, %s, %s)
                on conflict (user_email, agent_slug) do update set
                  expires_at = excluded.expires_at,
                  source_subscription_id = excluded.source_subscription_id
                """,
                (email, agent_slug, expires_at, sub_id),
            )

# ---- health & env
@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/check-env")
def check_env():
    return {
        "LOG_LEVEL": os.getenv("LOG_LEVEL"),
        "DATABASE_URL_start": (os.getenv("DATABASE_URL", "")[:12] or None),
        "THRIVECART_SECRET_start": (os.getenv("THRIVECART_SECRET", "")[:4] or None),
    }

# ---- debug routes
@app.get("/__routes")
def __routes():
    return [getattr(r, "path", None) for r in app.routes]

# ---- ThriveCart verify
@app.head("/billing/thrivecart")
def tc_head(): return Response(status_code=200)

@app.get("/billing/thrivecart")
def tc_get(): return {"ok": True}

EVENT_TO_STATUS = {
    "order.success": "active",
    "order.subscription_payment": "active",
    "order.subscription_resumed": "resumed",
    "order.subscription_cancelled": "cancelled",
    "order.subscription_paused": "paused",
    "order.rebill_failed": "past_due",
    "order.refund": "refunded",
}

@app.post("/billing/thrivecart")
async def thrivecart(request: Request):
    # form เป็นค่า default ของ ThriveCart
    try:
        data = dict(await request.form())
    except Exception:
        try:
            data = await request.json()
        except Exception:
            data = {}
    logger.info("Incoming ThriveCart keys: %s", list(data.keys()))

    secret = os.getenv("THRIVECART_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Server missing THRIVECART_SECRET")
    provided = data.get("thrivecart_secret") or data.get("secret") or data.get("signature")
    if provided != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    event = (data.get("event") or "").strip()
    email = (data.get("customer[email]") or data.get("email") or "").strip().lower()
    sub_id = (data.get("subscription[id]") or data.get("order_id") or data.get("invoice_id") or "tc-unknown").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Missing customer[email]")

    status = EVENT_TO_STATUS.get(event, "active")

    sku = derive_sku(data)
    if not sku:
        raise HTTPException(status_code=400, detail="Missing SKU (or fulfillment[url])")

    code = AGENT_SKU_TO_CODE.get(sku) or AGENT_SKU_TO_CODE.get(sku.lower())
    agent_slug = None
    if code:
        agent_slug = {v: k for k, v in AGENT_SLUG_TO_CODE.items()}.get(code)

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=500, detail="Missing DATABASE_URL")

    with psycopg.connect(dsn, autocommit=True) as db:
        upsert(db, email=email, sub_id=sub_id, sku=sku, status=status, expires_at=None, agent_slug=agent_slug)

    return JSONResponse({"ok": True})
