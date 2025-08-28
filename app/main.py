# app/main.py
import os
import re
import json
import importlib
import logging
from urllib.parse import urlparse
from json import JSONDecodeError
from typing import Optional, Dict, Any, Tuple

from fastapi import FastAPI, HTTPException, Request, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

# ---------- Pydantic request model (with safe fallback) ----------
try:
    from app.models import RunAgentRequest
except Exception:
    from typing import Optional, Dict, Any
    from pydantic import BaseModel, Field, ConfigDict, EmailStr

    class RunAgentRequest(BaseModel):
        email: EmailStr = Field(..., description="End-user email (UPN) used for entitlement check")
        payload: Optional[Dict[str, Any]] = Field(default=None, description="Agent-specific inputs")
        model_config = ConfigDict(extra="forbid")

from app.auth import require_api_key

# ---------- logging ----------
def _env_log_level(default: str = "INFO") -> int:
    lvl = str(os.getenv("LOG_LEVEL", default)).strip()
    if lvl.isdigit():
        return int(lvl)
    return getattr(logging, lvl.upper(), logging.INFO)

logging.basicConfig(
    level=_env_log_level(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("thanyaaura.gateway")

# ---------- agents resolver (optional external table) ----------
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

# ---------- fallback agent SKU map (base + variants) ----------
_BASE_FALLBACK = {
    "cfs": "SINGLE_CF_AI_AGENT",
    "cfp": "PROJECT_CF_AI_AGENT",
    "cfpr": "ENTERPRISE_CF_AI_AGENT",
    "single_cf": "SINGLE_CF_AI_AGENT",
    "project_cf": "PROJECT_CF_AI_AGENT",
    "enterprise_cf": "ENTERPRISE_CF_AI_AGENT",
    "revs": "REVENUE_STANDARD",
    "revp": "REVENUE_INTERMEDIATE",
    "revpr": "REVENUE_ADVANCE",
    "revenue_standard": "REVENUE_STANDARD",
    "revenue_intermediate": "REVENUE_INTERMEDIATE",
    "revenue_advance": "REVENUE_ADVANCE",
    "capexs": "CAPEX_STANDARD",
    "capexp": "CAPEX_PLUS",
    "capexpr": "CAPEX_PREMIUM",
    "capex_standard": "CAPEX_STANDARD",
    "capex_plus": "CAPEX_PLUS",
    "capex_premium": "CAPEX_PREMIUM",
    "fxs": "FX_STANDARD",
    "fxp": "FX_PLUS",
    "fxpr": "FX_PREMIUM",
    "fx_standard": "FX_STANDARD",
    "fx_plus": "FX_PLUS",
    "fx_premium": "FX_PREMIUM",
    "costs": "COST_STANDARD",
    "costp": "COST_PLUS",
    "costpr": "COST_PREMIUM",
    "cost_standard": "COST_STANDARD",
    "cost_plus": "COST_PLUS",
    "cost_premium": "COST_PREMIUM",
    "buds": "BUDGET_STANDARD",
    "budp": "BUDGET_PLUS",
    "budpr": "BUDGET_PREMIUM",
    "budget_standard": "BUDGET_STANDARD",
    "budget_plus": "BUDGET_PLUS",
    "budget_premium": "BUDGET_PREMIUM",
    "reps": "REPORT_STANDARD",
    "repp": "REPORT_PLUS",
    "reppr": "REPORT_PREMIUM",
    "report_standard": "REPORT_STANDARD",
    "report_plus": "REPORT_PLUS",
    "report_premium": "REPORT_PREMIUM",
    "vars": "VARIANCE_STANDARD",
    "varp": "VARIANCE_PLUS",
    "varpr": "VARIANCE_PREMIUM",
    "variance_standard": "VARIANCE_STANDARD",
    "variance_plus": "VARIANCE_PLUS",
    "variance_premium": "VARIANCE_PREMIUM",
    "mars": "MARGIN_STANDARD",
    "marp": "MARGIN_PLUS",
    "marpr": "MARGIN_PREMIUM",
    "margin_standard": "MARGIN_STANDARD",
    "margin_plus": "MARGIN_PLUS",
    "margin_premium": "MARGIN_PREMIUM",
    "fors": "FORECAST_STANDARD",
    "forp": "FORECAST_PLUS",
    "forpr": "FORECAST_PREMIUM",
    "forecast_standard": "FORECAST_STANDARD",
    "forecast_plus": "FORECAST_PLUS",
    "forecast_premium": "FORECAST_PREMIUM",
    "decs": "DECISION_STANDARD",
    "decp": "DECISION_PLUS",
    "decpr": "DECISION_PREMIUM",
    "decision_standard": "DECISION_STANDARD",
    "decision_plus": "DECISION_PLUS",
    "decision_premium": "DECISION_PREMIUM",
}
FALLBACK_SKU_TO_AGENT = dict(_BASE_FALLBACK)
for k, v in list(_BASE_FALLBACK.items()):
    FALLBACK_SKU_TO_AGENT[f"module-0-{k}"] = v
    FALLBACK_SKU_TO_AGENT[f"{k}_gemini"] = v
    FALLBACK_SKU_TO_AGENT[f"{k}_ms"] = v

FALLBACK_SKU_TO_AGENT.update(
    {
        "en_standard": "ENTERPRISE_LICENSE_STANDARD",
        "en_professional": "ENTERPRISE_LICENSE_PRO",
        "en_unlimited": "ENTERPRISE_LICENSE_UNLIMITED",
    }
)

_BASE_TIER = {
    "standard": "STANDARD",
    "plus": "PLUS",
    "premium": "PREMIUM",
    "tier_standard": "STANDARD",
    "tier_plus": "PLUS",
    "tier_premium": "PREMIUM",
}
TIER_SKU_TO_CODE = dict(_BASE_TIER)
for k, v in list(_BASE_TIER.items()):
    TIER_SKU_TO_CODE[f"module-0-{k}"] = v

# ---------- OPTIONAL entitlement modules ----------
try:
    from app import entitlements as ent_resolver  # optional
    from app import enterprise as enterprise_api  # optional
except Exception as e:
    ent_resolver = None
    enterprise_api = None
    log.warning("Entitlements modules not loaded (%s). Entitlement endpoints will degrade gracefully.", e)

try:
    from app.enterprise_access import check_entitlement  # gating (legacy)
except Exception as e:
    check_entitlement = None
    log.warning("enterprise_access.check_entitlement not available (%s).", e)

app = FastAPI(title="Thanyaaura Gateway", version="1.9.2")

# ---------- CORS ----------
def _parse_csv_env(name: str, default_list: list[str]) -> list[str]:
    s = os.getenv(name)
    if not s:
        return default_list
    return [x.strip() for x in s.split(",") if x.strip()]

ALLOWED_ORIGINS = _parse_csv_env(
    "CORS_ORIGINS",
    [
        "https://api.thanyaaura.com",
        "https://www.thanyaaura.com",
        "https://app.thanyaaura.com",
        "https://thanyaaura-gateway.onrender.com",
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------- Helpers ----------------------
def _drop_module0(s: str) -> str:
    s = (s or "").strip().lower()
    return s[9:] if s.startswith("module-0-") else s

def derive_sku_from_url(url_str: Optional[str]) -> Optional[str]:
    if not url_str:
        return None
    try:
        path = urlparse(url_str).path.lower()
        m = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
        return m.group(1) if m else None
    except Exception:
        return None

def derive_sku(data: Dict[str, Any]) -> Optional[str]:
    sku = data.get("sku") or data.get("passthrough[sku]") or data.get("passthrough")
    if sku:
        return _drop_module0(str(sku))
    f_url = (data.get("fulfillment[url]") or data.get("fulfillment_url") or data.get("fulfillment"))
    return derive_sku_from_url(f_url)

def _norm_platform_tag(tag: Optional[str]) -> Optional[str]:
    if not tag:
        return None
    t = str(tag).strip()
    u = t.upper()
    if u in ("MS", "MICROSOFT", "COPILOT") or u.startswith("COPILOT"):
        return "Copilot"
    if u.startswith("GEMINI"):
        return "Gemini"
    if u in ("GPT", "OPENAI", "CHATGPT"):
        return "GPT"
    return t

def derive_platform_from_sku(sku: Optional[str]) -> str:
    if not sku:
        return "unknown"
    s = (sku or "").lower()
    if s.endswith("_gemini"):
        return "Gemini"
    if s.endswith("_ms"):
        return "Copilot"
    if s.startswith("en_"):  # ENTERPRISE LICENSES → canonicalize to "Copilot"
        return "Copilot"
    return "GPT"

def _resolve_with_table(sku: str) -> Optional[str]:
    if not isinstance(AGENT_SKU_TO_AGENT, dict) or not AGENT_SKU_TO_AGENT:
        return None
    s = (sku or "").strip().lower()
    return (
        AGENT_SKU_TO_AGENT.get(s)
        or AGENT_SKU_TO_AGENT.get(_drop_module0(s))
        or AGENT_SKU_TO_AGENT.get(f"module-0-{_drop_module0(s)}")
    )

def _resolve_with_fallback(sku: str) -> Optional[str]:
    s = (sku or "").strip().lower()
    return (
        FALLBACK_SKU_TO_AGENT.get(s)
        or FALLBACK_SKU_TO_AGENT.get(_drop_module0(s))
        or FALLBACK_SKU_TO_AGENT.get(f"module-0-{_drop_module0(s)}")
    )

def resolve_agent_slug(sku: str) -> Optional[str]:
    if callable(get_agent_slug_from_sku):
        try:
            agent = get_agent_slug_from_sku(sku)
            if agent:
                return agent
        except Exception as ex:
            log.warning("Resolver error: %s", ex)
    return _resolve_with_table(sku) or _resolve_with_fallback(sku)

def resolve_tier_code(sku: str) -> Optional[str]:
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

# ===========================================================
# Enterprise fallback gating (ใช้เมื่อ legacy checker ไม่ผ่าน)
# ===========================================================
STANDARD_BASE: set[str] = {
    "cfs", "cfp", "cfpr",           # cashflow family considered STANDARD in your matrix
    "revs", "capexs", "fxs", "costs",
    "buds", "reps", "vars", "mars", "fors", "decs",
}

def _enterprise_allows(email: str, short_sku: str) -> Tuple[bool, str]:
    """
    ใช้ entitlement จาก app.enterprise เพื่อ gate เฉพาะ Copilot (*_ms)
      - en_standard      -> อนุญาตเฉพาะ STANDARD_BASE เป็น *_ms
      - en_professional  -> อนุญาตทั้งหมด *_ms
      - en_unlimited     -> อนุญาตทั้งหมด *_ms
    """
    if not enterprise_api:
        return False, "enterprise-api-missing"

    platform = derive_platform_from_sku(short_sku)
    if platform != "Copilot":
        return False, "not-copilot"

    try:
        ent = enterprise_api.entitlements_for_email(email)
    except Exception as e:
        log.warning("enterprise_api.entitlements_for_email error: %s", e)
        return False, "enterprise-error"

    if not ent or ent.get("scope") != "enterprise":
        return False, "no-enterprise-plan"

    plan = (ent.get("plan") or "").strip()
    base = _drop_module0(short_sku).replace("_ms", "")
    if plan == "Enterprise-Standard":
        return (base in STANDARD_BASE), "enterprise-standard-allow" if (base in STANDARD_BASE) else "enterprise-standard-block"
    # Professional/Unlimited
    return True, "enterprise-all-allow"

# ===== NEW: toggle & robust entitlement check =====
DISABLE_ENTITLEMENT_CHECK = os.getenv("DISABLE_ENTITLEMENT_CHECK", "0") == "1"

def require_entitlement_or_403(user_email: str, sku: str):
    short = _drop_module0(sku)
    agent_slug = resolve_agent_slug(short) or short.upper()
    platform = derive_platform_from_sku(short)

    # bypass flag for demo
    if DISABLE_ENTITLEMENT_CHECK:
        return agent_slug, platform

    # 1) ลอง legacy checker ก่อน
    if check_entitlement:
        candidates = [
            (agent_slug, platform),
            (short, platform),
            (agent_slug.lower(), platform),
            (agent_slug.upper(), platform),
        ]
        for cand, pf in candidates:
            try:
                if check_entitlement(user_email, cand, pf):
                    return agent_slug, platform
            except Exception as e:
                log.warning("check_entitlement error on %s/%s: %s", cand, pf, e)
    else:
        log.info("check_entitlement missing, using enterprise fallback if possible.")

    # 2) Fallback: enterprise gating (เฉพาะ Copilot)
    ok, reason = _enterprise_allows(user_email, short)
    if ok:
        return agent_slug, platform

    raise HTTPException(status_code=403, detail=f"No entitlement for this agent/platform ({reason}).")

# ---------------------- Basics ----------------------
@app.get("/")
async def root():
    return {
        "name": "Thanyaaura Gateway",
        "version": getattr(app, "version", None),
        "docs": "/docs",
        "endpoints_hint": [
            "/health",
            "/healthz",
            "/routes",
            "/debug/*",
            "/billing/thrivecart",
            "/entitlements/{email}",
            "/entitlements/company/{domain}",
            "/agents/{sku}/run",
        ],
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/routes")
async def routes():
    return [r.path for r in app.routes if isinstance(r, APIRoute)]

# ---------------------- Debug (conditional via ENV) ----------------------
IS_DEBUG_ROUTES = os.getenv("ENABLE_DEBUG_ROUTES", "0") == "1"

if IS_DEBUG_ROUTES:
    @app.get("/debug/resolve")
    async def debug_resolve(sku: str):
        short_sku = _drop_module0(sku)
        return {
            "sku_in": sku,
            "sku_short": short_sku,
            "agent_slug": resolve_agent_slug(short_sku),
            "tier_code": resolve_tier_code(short_sku),
            "platform": derive_platform_from_sku(short_sku),
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

    @app.get("/debug/check-entitlement")
    async def debug_check_entitlement(email: str, sku: str):
        short = _drop_module0(sku)
        slug = resolve_agent_slug(short) or short.upper()
        plat = derive_platform_from_sku(short)

        res_slug = False
        res_sku = False
        err_slug = None
        err_sku = None
        if check_entitlement:
            try:
                res_slug = check_entitlement(email, slug, plat)
            except Exception as e1:
                err_slug = str(e1)
            try:
                res_sku = check_entitlement(email, short, plat)
            except Exception as e2:
                err_sku = str(e2)

        ent_ok, ent_reason = _enterprise_allows(email, short)

        return {
            "ok": bool(res_slug or res_sku or ent_ok),
            "agent_slug": slug,
            "sku": short,
            "platform": plat,
            "checked": {"slug": res_slug, "sku": res_sku, "enterprise": ent_ok},
            "errors": {"slug": err_slug, "sku": err_sku, "enterprise": None if ent_ok else ent_reason},
        }

# ---------------------- Entitlements APIs ----------------------
@app.get("/entitlements/{email}")
async def entitlements(email: str):
    if not ent_resolver:
        raise HTTPException(status_code=501, detail="Entitlements resolver not available.")
    result = ent_resolver.resolve_entitlements(
        email, precedence=os.getenv("ENT_PRECEDENCE", "rank")
    )
    result["links"] = {
        "gpt": os.getenv("LINK_GPT", "https://chat.openai.com/"),
        "gemini": os.getenv("LINK_GEMINI", "https://gemini.google.com/"),
        "copilot": os.getenv("LINK_COPILOT", "https://copilot.microsoft.com/"),
    }
    return result

@app.get("/entitlements/company/{domain}")
async def entitlements_company(domain: str):
    if not enterprise_api:
        raise HTTPException(status_code=501, detail="Enterprise API not available.")
    ent = enterprise_api.entitlements_for_domain(domain)
    if not ent:
        return {"company_domain": domain, "scope": "unknown"}
    ent["links"] = {
        "gpt": os.getenv("LINK_GPT", "https://chat.openai.com/"),
        "gemini": os.getenv("LINK_GEMINI", "https://gemini.google.com/"),
        "copilot": os.getenv("LINK_COPILOT", "https://copilot.microsoft.com/"),
    }
    return ent

# ---------------------- Agents: run (with entitlement) ----------------------
@app.post(
    "/agents/{sku}/run",
    summary="Run a Finance Agent",
    tags=["agents"],
    dependencies=[Depends(require_api_key)],
)
async def run_agent(sku: str, req: RunAgentRequest):
    user_email = req.email
    agent_slug, platform = require_entitlement_or_403(user_email, sku)
    # TODO: call the real business logic here
    return {"ok": True, "agent": agent_slug, "platform": platform, "echo": (req.payload or {})}

# ---------------------- Payload reader (for ThriveCart) ----------------------
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

# ---------------------- ThriveCart webhook ----------------------
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

    short_sku = _drop_module0(sku)
    tier_code = resolve_tier_code(short_sku)
    agent_slug = None if tier_code else resolve_agent_slug(short_sku)
    if not tier_code and not agent_slug and not short_sku.startswith("en_"):
        raise HTTPException(status_code=400, detail=f"Unknown SKU: {short_sku}")

    order_id = data.get("order_id") or data.get("invoice_id")
    email = data.get("customer[email]") or data.get("email")
    if not order_id or not email:
        raise HTTPException(status_code=400, detail="Missing order_id or customer[email]")

    # Platform canonicalization
    if short_sku.startswith("en_"):
        platform = "Copilot"
    else:
        posted_platform = _norm_platform_tag(data.get("platform"))
        platform = posted_platform or derive_platform_from_sku(short_sku)

    # Optional hook (best-effort)
    if enterprise_api:
        try:
            enterprise_api.apply_thrivecart_event(data)  # no-op in current enterprise.py
        except Exception as e:
            log.warning("apply_thrivecart_event failed: %s", e)

    dbmod = _db()
    try:
        if short_sku.startswith("en_"):
            # db.upsert_enterprise_license ถูกอัปเดตให้เขียนลง enterprise_licenses แล้ว
            await run_in_threadpool(
                dbmod.upsert_enterprise_license, order_id, email, short_sku, agent_slug, platform
            )
            ttype = "ENTERPRISE"
        elif tier_code:
            await run_in_threadpool(
                dbmod.upsert_tier_subscription, order_id, email, short_sku, tier_code, platform
            )
            ttype = "TIER"
        else:
            await run_in_threadpool(
                dbmod.upsert_subscription_and_entitlement,
                order_id,
                email,
                short_sku,
                agent_slug,
                platform,
            )
            ttype = "AGENT"
    except Exception as ex_db:
        raise HTTPException(status_code=500, detail=f"DB error: {ex_db}")

    return {
        "ok": True,
        "sku": short_sku,
        "platform": platform,
        "type": ttype,
        "tier_code": tier_code,
        "agent_slug": agent_slug,
        "event": data.get("event"),
        "order_id": order_id,
        "email": email,
    }

# ---------------------- Startup ----------------------
@app.on_event("startup")
async def ensure_admin_on_startup():
    try:
        dbmod = importlib.import_module("app.db")
        await run_in_threadpool(dbmod.ensure_permanent_admin_user)
    except Exception as ex:
        log.warning("Could not ensure permanent admin user: %s", ex)

# ---------------------- HEAD / (avoid 405 in probes) ----------------------
@app.head("/")
def head_root():
    return Response(status_code=204)
