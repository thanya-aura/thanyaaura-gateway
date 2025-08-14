# app/main.py — Gateway app with robust SKU resolver and debug endpoints

import os
import re
import json
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request

# --- try import real resolver/table from agents.py (Excel-aligned expected) ---
try:
    from app.agents import get_agent_slug_from_sku, AGENT_SKU_TO_AGENT
except Exception:
    get_agent_slug_from_sku = None
    AGENT_SKU_TO_AGENT = {}

# --- full fallback covering all 33 agents (short & long names + module-0- prefix) ---

_BASE_FALLBACK = {
    # Cashflow (3)
    "cfs":   "SINGLE_CF_AI_AGENT",
    "cfp":   "PROJECT_CF_AI_AGENT",
    "cfpr":  "ENTERPRISE_CF_AI_AGENT",
    "single_cf":   "SINGLE_CF_AI_AGENT",
    "project_cf":    "PROJECT_CF_AI_AGENT",
    "enterprise_cf": "ENTERPRISE_CF_AI_AGENT",

    # Revenue (3)
    "revs":  "REVENUE_STANDARD",
    "revp":  "REVENUE_INTERMEDIATE",
    "revpr": "REVENUE_ADVANCE",
    "revenue_standard":     "REVENUE_STANDARD",
    "revenue_intermediate": "REVENUE_INTERMEDIATE",
    "revenue_advance":      "REVENUE_ADVANCE",

    # CAPEX (3)
    "capexs":  "CAPEX_STANDARD",
    "capexp":  "CAPEX_PLUS",
    "capexpr": "CAPEX_PREMIUM",
    "capex_standard": "CAPEX_STANDARD",
    "capex_plus":     "CAPEX_PLUS",
    "capex_premium":  "CAPEX_PREMIUM",

    # FX (3)
    "fxs":  "FX_STANDARD",
    "fxp":  "FX_PLUS",
    "fxpr": "FX_PREMIUM",
    "fx_standard": "FX_STANDARD",
    "fx_plus":     "FX_PLUS",
    "fx_premium":  "FX_PREMIUM",

    # COST (3)
    "costs":  "COST_STANDARD",
    "costp":  "COST_PLUS",
    "costpr": "COST_PREMIUM",
    "cost_standard": "COST_STANDARD",
    "cost_plus":     "COST_PLUS",
    "cost_premium":  "COST_PREMIUM",

    # BUDGET (3)
    "buds":  "BUDGET_STANDARD",
    "budp":  "BUDGET_PLUS",
    "budpr": "BUDGET_PREMIUM",
    "budget_standard": "BUDGET_STANDARD",
    "budget_plus":     "BUDGET_PLUS",
    "budget_premium":  "BUDGET_PREMIUM",

    # REPORT (3)
    "reps":  "REPORT_STANDARD",
    "repp":  "REPORT_PLUS",
    "reppr": "REPORT_PREMIUM",
    "report_standard": "REPORT_STANDARD",
    "report_plus":     "REPORT_PLUS",
    "report_premium":  "REPORT_PREMIUM",

    # VARIANCE (3)
    "vars":  "VARIANCE_STANDARD",
    "varp":  "VARIANCE_PLUS",
    "varpr": "VARIANCE_PREMIUM",
    "variance_standard": "VARIANCE_STANDARD",
    "variance_plus":     "VARIANCE_PLUS",
    "variance_premium":  "VARIANCE_PREMIUM",

    # MARGIN (3)
    "mars":  "MARGIN_STANDARD",
    "marp":  "MARGIN_PLUS",
    "marpr": "MARGIN_PREMIUM",
    "margin_standard": "MARGIN_STANDARD",
    "margin_plus":     "MARGIN_PLUS",
    "margin_premium":  "MARGIN_PREMIUM",

    # FORECAST (3)
    "fors":  "FORECAST_STANDARD",
    "forp":  "FORECAST_PLUS",
    "forpr": "FORECAST_PREMIUM",
    "forecast_standard": "FORECAST_STANDARD",
    "forecast_plus":     "FORECAST_PLUS",
    "forecast_premium":  "FORECAST_PREMIUM",

    # DECISION (3)
    "decs":  "DECISION_STANDARD",
    "decp":  "DECISION_PLUS",
    "decpr": "DECISION_PREMIUM",
    "decision_standard": "DECISION_STANDARD",
    "decision_plus":     "DECISION_PLUS",
    "decision_premium":  "DECISION_PREMIUM",
}

# auto-add module-0- prefixed variants
FALLBACK_SKU_TO_AGENT = dict(_BASE_FALLBACK)
for k, v in list(_BASE_FALLBACK.items()):
    FALLBACK_SKU_TO_AGENT[f"module-0-{k}"] = v


app = FastAPI(title="Thanyaaura Gateway", version="1.1.0")

# -----------------------
# Helpers: SKU extraction
# -----------------------
def _drop_module0(s: str) -> str:
    s = (s or "").strip().lower()
    return s[9:] if s.startswith("module-0-") else s

def derive_sku_from_url(url_str: str | None) -> str | None:
    if not url_str:
        return None
    try:
        path = urlparse(url_str).path.lower()
        m = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
        return m.group(1) if m else None
    except Exception:
        return None

def derive_sku(data: dict) -> str | None:
    """
    Priority:
      1) 'sku' or 'passthrough[sku]' (normalized & drop 'module-0-')
      2) from fulfillment url: fulfillment[url] / fulfillment_url / fulfillment
    """
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        return _drop_module0(sku)

    f_url = data.get("fulfillment[url]") or data.get("fulfillment_url") or data.get("fulfillment")
    slug = derive_sku_from_url(f_url)
    return slug

async def read_payload(request: Request) -> dict:
    """
    Accepts application/json and application/x-www-form-urlencoded
    """
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            raw = await request.body()
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    form = await request.form()
    return dict(form)

# -----------------------
# Resolver (layered)
# -----------------------
def _resolve_with_table(sku: str) -> str | None:
    """Try direct table lookup if AGENT_SKU_TO_AGENT is available."""
    if not AGENT_SKU_TO_AGENT:
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
    """
    Final resolver order:
      1) get_agent_slug_from_sku (agents.py)
      2) AGENT_SKU_TO_AGENT direct lookup (agents.py)
      3) FALLBACK_SKU_TO_AGENT
    """
    if callable(get_agent_slug_from_sku):
        agent = get_agent_slug_from_sku(sku)
        if agent:
            return agent
    agent = _resolve_with_table(sku)
    if agent:
        return agent
    return _resolve_with_fallback(sku)

# -----------------------
# Endpoints
# -----------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/routes")
async def routes():
    return [r.path for r in app.routes]

@app.get("/debug/resolve")
async def debug_resolve(sku: str):
    """
    Quick check: accepts 'cfp', 'module-0-cfp', 'project_cf', etc.
    """
    return {"sku_in": sku, "agent_slug": resolve_agent_slug(sku)}

@app.get("/debug/sku-keys")
async def debug_sku_keys():
    """
    Known keys sample from both AGENT_SKU_TO_AGENT (if present) and fallback table.
    """
    keys = set()
    try:
        keys.update(list(AGENT_SKU_TO_AGENT.keys()))
    except Exception:
        pass
    keys.update(FALLBACK_SKU_TO_AGENT.keys())
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
    except Exception as e:
        return {"loaded": False, "error": str(e)}

@app.post("/billing/thrivecart")
async def billing_thrivecart(request: Request):
    """
    ThriveCart webhook endpoint
    """
    data = await read_payload(request)

    # Optional secret check (uncomment to enforce)
    # secret_in  = data.get("thrivecart_secret") or request.headers.get("X-THRIVECART-SECRET")
    # secret_env = os.environ.get("THRIVECART_SECRET")
    # if not secret_in or not secret_env or secret_in != secret_env:
    #     raise HTTPException(status_code=401, detail="Unauthorized")

    # Extract SKU
    sku = derive_sku(data)
    if not sku:
        raise HTTPException(status_code=400, detail="Missing SKU (or fulfillment[url])")

    # Resolve -> agent_slug
    agent_slug = resolve_agent_slug(sku)
    if not agent_slug:
        # show small hint to debug
        known = []
        try:
            known.extend(list(AGENT_SKU_TO_AGENT.keys())[:6])
        except Exception:
            pass
        known.extend(list(FALLBACK_SKU_TO_AGENT.keys())[:6])
        raise HTTPException(status_code=400, detail=f"Unknown SKU: {sku}. Try one of: {known} ...")

    # TODO: upsert subscriptions & entitlements as per your original logic.
    return {
        "ok": True,
        "sku": _drop_module0(sku),
        "agent_slug": agent_slug,
        "event": data.get("event"),
        "order_id": data.get("order_id") or data.get("invoice_id"),
        "email": data.get("customer[email]") or data.get("email"),
    }
