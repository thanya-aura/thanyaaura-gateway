# app/main.py — with built-in fallback resolver (CF family) + existing endpoints

import os
import re
import json
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request

# --- try import real resolver from agents.py ---
try:
    from app.agents import get_agent_slug_from_sku, AGENT_SKU_TO_AGENT
except Exception:
    get_agent_slug_from_sku = None
    AGENT_SKU_TO_AGENT = {}

# --- minimal fallback (covers cashflow family + common aliases) ---
FALLBACK_SKU_TO_AGENT = {
    # canonical
    "cfs": "SINGLE_CF_AI_AGENT",
    "cfp": "PROJECT_CF_AI_AGENT",
    "cfpr": "ENTERPRISE_CF_AI_AGENT",
    # aliases
    "module-0-cfs": "SINGLE_CF_AI_AGENT",
    "module-0-cfp": "PROJECT_CF_AI_AGENT",
    "module-0-cfpr": "ENTERPRISE_CF_AI_AGENT",
    "project_cf": "PROJECT_CF_AI_AGENT",
    "enterprise_cf": "ENTERPRISE_CF_AI_AGENT",
}

def _fallback_resolve(sku: str) -> str | None:
    s = (sku or "").strip().lower()
    if s.startswith("module-0-"):
        s = s[9:]
    # try short, then prefixed, then legacy
    return (
        FALLBACK_SKU_TO_AGENT.get(s)
        or FALLBACK_SKU_TO_AGENT.get(f"module-0-{s}")
        or (s == "project_cf" and "PROJECT_CF_AI_AGENT")
        or (s == "enterprise_cf" and "ENTERPRISE_CF_AI_AGENT")
    )

app = FastAPI(title="Thanyaaura Gateway", version="1.0.0")

def _drop_module_prefix(s: str) -> str:
    s = (s or "").strip().lower()
    if s.startswith("module-0-"):
        s = s[9:]
    return s

def derive_sku_from_url(url_str: str | None) -> str | None:
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
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        return _drop_module_prefix(sku)
    f_url = data.get("fulfillment[url]") or data.get("fulfillment_url") or data.get("fulfillment")
    return derive_sku_from_url(f_url)

async def read_payload(request: Request) -> dict:
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            body = await request.body()
            return json.loads(body.decode("utf-8") or "{}")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
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
    if callable(get_agent_slug_from_sku):
        agent = get_agent_slug_from_sku(sku)
    else:
        agent = _fallback_resolve(sku)
    return {"sku_in": sku, "agent_slug": agent}

@app.get("/debug/sku-keys")
async def debug_sku_keys():
    keys = set()
    try:
        keys.update(list(AGENT_SKU_TO_AGENT.keys()))
    except Exception:
        pass
    keys.update(FALLBACK_SKU_TO_AGENT.keys())
    return sorted(keys)

@app.post("/billing/thrivecart")
async def billing_thrivecart(request: Request):
    data = await read_payload(request)

    # Optional secret check (uncomment to enforce)
    # secret_in  = data.get("thrivecart_secret") or request.headers.get("X-THRIVECART-SECRET")
    # secret_env = os.environ.get("THRIVECART_SECRET")
    # if not secret_in or not secret_env or secret_in != secret_env:
    #     raise HTTPException(status_code=401, detail="Unauthorized")

    sku = derive_sku(data)
    if not sku:
        raise HTTPException(status_code=400, detail="Missing SKU (or fulfillment[url])")

    if callable(get_agent_slug_from_sku):
        agent_slug = get_agent_slug_from_sku(sku)
    else:
        agent_slug = _fallback_resolve(sku)

    if not agent_slug:
        known = (list(getattr(AGENT_SKU_TO_AGENT, "keys", lambda: [])())[:6]
                 if AGENT_SKU_TO_AGENT else [])
        known += list(FALLBACK_SKU_TO_AGENT.keys())[:6]
        raise HTTPException(status_code=400, detail=f"Unknown SKU: {sku}. Try: {known} ...")

    # TODO: upsert subscriptions + entitlements (ของเดิมคุณ)
    return {
        "ok": True,
        "sku": sku,
        "agent_slug": agent_slug,
        "event": data.get("event"),
        "order_id": data.get("order_id") or data.get("invoice_id"),
        "email": data.get("customer[email]") or data.get("email"),
    }
