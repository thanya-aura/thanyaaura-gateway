# main.py
import os
import re
import json
import importlib
import logging
from urllib.parse import urlparse
from json import JSONDecodeError
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

log = logging.getLogger("thanyaaura.gateway")
logging.basicConfig(level=logging.INFO)

# ===== Try import real resolver/table from agents.py =====
try:
    from app.agents import get_agent_slug_from_sku, AGENT_SKU_TO_AGENT  # noqa
    log.info("Loaded resolver from app.agents (keys=%s)", len(AGENT_SKU_TO_AGENT or {}))
except ImportError as ex_import:
    log.warning("agents.py not loaded, using fallback (%s)", ex_import)
    get_agent_slug_from_sku = None
    AGENT_SKU_TO_AGENT = {}
except Exception as ex_generic:
    log.warning("Unexpected error loading agents.py: %s", ex_generic)
    get_agent_slug_from_sku = None
    AGENT_SKU_TO_AGENT = {}

# ===== FULL FALLBACK (33 agents) =====
_BASE_FALLBACK = {
    # Cashflow (3) + aliases
    "cfs": "SINGLE_CF_AI_AGENT", "cfp": "PROJECT_CF_AI_AGENT", "cfpr": "ENTERPRISE_CF_AI_AGENT",
    "single_cf": "SINGLE_CF_AI_AGENT", "project_cf": "PROJECT_CF_AI_AGENT", "enterprise_cf": "ENTERPRISE_CF_AI_AGENT",
    # Revenue (3)
    "revs": "REVENUE_STANDARD", "revp": "REVENUE_INTERMEDIATE", "revpr": "REVENUE_ADVANCE",
    "revenue_standard": "REVENUE_STANDARD", "revenue_intermediate": "REVENUE_INTERMEDIATE", "revenue_advance": "REVENUE_ADVANCE",
    # CAPEX (3)
    "capexs": "CAPEX_STANDARD", "capexp": "CAPEX_PLUS", "capexpr": "CAPEX_PREMIUM",
    "capex_standard": "CAPEX_STANDARD", "capex_plus": "CAPEX_PLUS", "capex_premium": "CAPEX_PREMIUM",
    # FX (3)
    "fxs": "FX_STANDARD", "fxp": "FX_PLUS", "fxpr": "FX_PREMIUM",
    "fx_standard": "FX_STANDARD", "fx_plus": "FX_PLUS", "fx_premium": "FX_PREMIUM",
    # COST (3)
    "costs": "COST_STANDARD", "costp": "COST_PLUS", "costpr": "COST_PREMIUM",
    "cost_standard": "COST_STANDARD", "cost_plus": "COST_PLUS", "cost_premium": "COST_PREMIUM",
    # BUDGET (3)
    "buds": "BUDGET_STANDARD", "budp": "BUDGET_PLUS", "budpr": "BUDGET_PREMIUM",
    "budget_standard": "BUDGET_STANDARD", "budget_plus": "BUDGET_PLUS", "budget_premium": "BUDGET_PREMIUM",
    # REPORT (3)
    "reps": "REPORT_STANDARD", "repp": "REPORT_PLUS", "reppr": "REPORT_PREMIUM",
    "report_standard": "REPORT_STANDARD", "report_plus": "REPORT_PLUS", "report_premium": "REPORT_PREMIUM",
    # VARIANCE (3)
    "vars": "VARIANCE_STANDARD", "varp": "VARIANCE_PLUS", "varpr": "VARIANCE_PREMIUM",
    "variance_standard": "VARIANCE_STANDARD", "variance_plus": "VARIANCE_PLUS", "variance_premium": "VARIANCE_PREMIUM",
    # MARGIN (3)
    "mars": "MARGIN_STANDARD", "marp": "MARGIN_PLUS", "marpr": "MARGIN_PREMIUM",
    "margin_standard": "MARGIN_STANDARD", "margin_plus": "MARGIN_PLUS", "margin_premium": "MARGIN_PREMIUM",
    # FORECAST (3)
    "fors": "FORECAST_STANDARD", "forp": "FORECAST_PLUS", "forpr": "FORECAST_PREMIUM",
    "forecast_standard": "FORECAST_STANDARD", "forecast_plus": "FORECAST_PLUS", "forecast_premium": "FORECAST_PREMIUM",
    # DECISION (3)
    "decs": "DECISION_STANDARD", "decp": "DECISION_PLUS", "decpr": "DECISION_PREMIUM",
    "decision_standard": "DECISION_STANDARD", "decision_plus": "DECISION_PLUS", "decision_premium": "DECISION_PREMIUM",
}
FALLBACK_SKU_TO_AGENT = dict(_BASE_FALLBACK)
for k, v in list(_BASE_FALLBACK.items()):
    FALLBACK_SKU_TO_AGENT[f"module-0-{k}"] = v

# ===== Tier SKUs =====
_BASE_TIER = {
    "standard": "STANDARD", "plus": "PLUS", "premium": "PREMIUM",
    "tier_standard": "STANDARD", "tier_plus": "PLUS", "tier_premium": "PREMIUM",
}
TIER_SKU_TO_CODE = dict(_BASE_TIER)
for k, v in list(_BASE_TIER.items()):
    TIER_SKU_TO_CODE[f"module-0-{k}"] = v

app = FastAPI(title="Thanyaaura Gateway", version="1.5.0")

# ----------------------
# Helpers
# ----------------------
def _drop_module0(s: str) -> str:
    s = (s or "").strip().lower()
    return s[9:] if s.startswith("module-0-") else s

def derive_sku_from_url(url_str: str | None) -> str | None:
    if not url_str:
        return None
    try:
        path = urlparse(url_str).path.lower()
        match = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
        return match.group(1) if match else None
    except Exception:
        return None

def derive_sku(data: dict) -> str | None:
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        return _drop_module0(sku)
    f_url = data.get("fulfillment[url]") or data.get("fulfillment_url") or data.get("fulfillment")
    return derive_sku_from_url(f_url)

def _resolve_with_table(sku: str) -> str | None:
    if not isinstance(AGENT_SKU_TO_AGENT, dict) or not AGENT_SKU_TO_AGENT:
        return None
    s = (sku or "").strip().lower()
    return (
        AGENT_SKU_TO_AGENT.get(s)
        or AGENT_SKU_TO_AGENT.get(_drop_module0(s))
        or AGENT_SKU_TO_AGENT.get(f"module-0-{_drop_module0(s)}")
    )

def _resolve_with_fallback(sku: str) -> str | None:
    s = (sku or "").strip().lower()
    return (
        FALLBACK_SKU_TO_AGENT.get(s)
        or FALLBACK_SKU_TO_AGENT.get(_drop_module0(s))
        or FALLBACK_SKU_TO_AGENT.get(f"module-0-{_drop_module0(s)}")
    )

def resolve_agent_slug(sku: str) -> str | None:
    if callable(get_agent_slug_from_sku):
        try:
            agent = get_agent_slug_from_sku(sku)
            if agent:
                return agent
        except Exception as ex_resolver:
            log.warning("Resolver error: %s", ex_resolver)
    return _resolve_with_table(sku) or _resolve_with_fallback(sku)

def resolve_tier_code(sku: str) -> str | None:
    s = (sku or "").strip().lower()
    return (
        TIER_SKU_TO_CODE.get(s)
        or TIER_SKU_TO_CODE.get(_drop_module0(s))
        or TIER_SKU_TO_CODE.get(f"module-0-{_drop_module0(s)}")
    )

def _db():
    try:
        return importlib.import_module("app.db")
    except ImportError as ex_import:
        raise HTTPException(status_code=500, detail=f"DB module not available: {ex_import}")
    except Exception as ex_generic:
        raise HTTPException(status_code=500, detail=f"DB module error: {ex_generic}")

# ----------------------
# Routes
# ----------------------
@app.get("/")
async def root():
    return {
        "name": "Thanyaaura Gateway",
        "version": getattr(app, "version", None),
        "docs": "/docs",
        "endpoints_hint": ["/health", "/routes", "/debug/*", "/billing/thrivecart"],
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/routes")
async def routes():
    return [r.path for r in app.routes if isinstance(r, APIRoute)]

@app.get("/debug/resolve")
async def debug_resolve(sku: str):
    return {
        "sku_in": sku,
        "agent_slug": resolve_agent_slug(sku),
        "tier_code": resolve_tier_code(sku),
    }

@app.get("/debug/sku-keys")
async def debug_sku_keys():
    keys = set()
    if isinstance(AGENT_SKU_TO_AGENT, dict):
        keys.update(list(AGENT_SKU_TO_AGENT.keys()))
    keys.update(FALLBACK_SKU_TO_AGENT.keys())
    keys.update(TIER_SKU_TO_CODE.keys())
    return sorted(keys)

@app.get("/debug/agents-state")
async def debug_agents_state():
    try:
        from app import agents as _agents
        table = getattr(_agents, "AGENT_SKU_TO_AGENT", {})
        has_func = callable(getattr(_agents, "get_agent_slug_from_sku", None))
        sample = sorted(table.keys())[:20] if isinstance(table, dict) else []
        return {
            "loaded": True,
            "has_func": has_func,
            "keys_count": len(table) if isinstance(table, dict) else 0,
            "keys_sample": sample,
        }
    except Exception as ex_agents:
        return {"loaded": False, "error": str(ex_agents)}

@app.get("/debug/db-ping")
async def debug_db_ping():
    try:
        dbmod = _db()
        info = await run_in_threadpool(dbmod.ping_db)
        return info
    except Exception as ex_dbping:
        return {"ok": False, "error": str(ex_dbping)}

# ---- payload reader ----
async def read_payload(request: Request) -> dict:
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            raw = await request.body()
            return json.loads(raw.decode("utf-8") or "{}")
        except JSONDecodeError as e_json:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e_json
        except Exception as ex_json:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from ex_json
    try:
        form = await request.form()
        return dict(form)
    except Exception as ex_form:
        log.warning("Form parse error: %s", ex_form)
        return {}

@app.post("/billing/thrivecart")
async def billing_thrivecart(request: Request):
    data = await read_payload(request)

    secret_in = (
        data.get("thrivecart_secret")
        or request.headers.get("X-THRIVECART-SECRET")
        or request.query_params.get("thrivecart_secret")
    )
    secret_env = os.environ.get("THRIVECART_SECRET")
    if not secret_in or not secret_env or secret_in != secret_env:
        raise HTTPException(status_code=401, detail="Unauthorized")

    sku = derive_sku(data)
    if not sku:
        raise HTTPException(status_code=400, detail="Missing SKU (or fulfillment[url])")

    tier_code = resolve_tier_code(sku)
    agent_slug = None if tier_code else resolve_agent_slug(sku)
    if not tier_code and not agent_slug:
        raise HTTPException(status_code=400, detail=f"Unknown SKU: {sku}")

    order_id = data.get("order_id") or data.get("invoice_id")
    email = data.get("customer[email]") or data.get("email")
    if not order_id or not email:
        raise HTTPException(status_code=400, detail="Missing order_id or customer[email]")

    short_sku = _drop_module0(sku)

    dbmod = _db()
    try:
        if tier_code:
            await run_in_threadpool(dbmod.upsert_tier_subscription, order_id, email, short_sku, tier_code)
        else:
            await run_in_threadpool(dbmod.upsert_subscription_and_entitlement, order_id, email, short_sku, agent_slug)
    except Exception as ex_db:
        raise HTTPException(status_code=500, detail=f"DB error: {ex_db}")

    return {
        "ok": True,
        "sku": short_sku,
        "type": "TIER" if tier_code else "AGENT",
        "tier_code": tier_code,
        "agent_slug": agent_slug,
        "event": data.get("event"),
        "order_id": order_id,
        "email": email,
    }
