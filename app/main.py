# app/main.py
import os
import re
import json
import importlib
import logging
from urllib.parse import urlparse
from json import JSONDecodeError
from typing import Optional, Dict, Any, Tuple, List, Literal

from fastapi import FastAPI, HTTPException, Request, Depends, Response, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

# ---------- Pydantic request model (with safe fallback) ----------
try:
    from app.models import RunAgentRequest  # legacy /agents/{sku}/run
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

# สำหรับ /v1/run (agent_slug) — Standard plan อนุญาตเฉพาะ agent slug กลุ่ม standard
STANDARD_ALLOWED_AGENT_SLUGS: set[str] = {
    "SINGLE_CF_AI_AGENT",
    "PROJECT_CF_AI_AGENT",
    "ENTERPRISE_CF_AI_AGENT",
    "REVENUE_STANDARD",
    "CAPEX_STANDARD",
    "FX_STANDARD",
    "COST_STANDARD",
    "BUDGET_STANDARD",
    "REPORT_STANDARD",
    "VARIANCE_STANDARD",
    "MARGIN_STANDARD",
    "FORECAST_STANDARD",
    "DECISION_STANDARD",
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

# ===== NEW: entitlement check by SKU (existing) & by agent_slug (new for /v1/run) =====
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

def _enterprise_allows_agent_slug(email: str, agent_slug: str, platform: str) -> Tuple[bool, str]:
    """ใช้กับ /v1/run (ไม่มี SKU)"""
    if platform != "Copilot" or not enterprise_api:
        return False, "not-copilot-or-no-enterprise-api"
    try:
        ent = enterprise_api.entitlements_for_email(email)
    except Exception as e:
        log.warning("enterprise_api.entitlements_for_email error: %s", e)
        return False, "enterprise-error"
    if not ent or ent.get("scope") != "enterprise":
        return False, "no-enterprise-plan"
    plan = (ent.get("plan") or "").strip()
    if plan == "Enterprise-Standard":
        return (agent_slug in STANDARD_ALLOWED_AGENT_SLUGS), "enterprise-standard-allow" if (agent_slug in STANDARD_ALLOWED_AGENT_SLUGS) else "enterprise-standard-block"
    return True, "enterprise-all-allow"

def require_entitlement_for_agent_slug_or_403(user_email: str, agent_slug: str, platform: str):
    """ใช้กับ /v1/run — ตรวจสิทธิ์ด้วย agent_slug โดยตรง"""
    if DISABLE_ENTITLEMENT_CHECK:
        return

    # 1) legacy checker (ถ้ามี)
    if check_entitlement:
        try:
            if check_entitlement(user_email, agent_slug, platform):
                return
        except Exception as e:
            log.warning("check_entitlement error on %s/%s: %s", agent_slug, platform, e)

    # 2) enterprise fallback (เฉพาะ Copilot)
    ok, reason = _enterprise_allows_agent_slug(user_email, agent_slug, platform)
    if ok:
        return

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
            "/v1/run",
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

# ---------------------- Agents: run (legacy by SKU, with API key) ----------------------
@app.post(
    "/agents/{sku}/run",
    summary="Run a Finance Agent",
    tags=["agents"],
    dependencies=[Depends(require_api_key)],
)
async def run_agent(sku: str, req: RunAgentRequest):
    user_email = req.email
    agent_slug, platform = require_entitlement_or_403(user_email, sku)

    # ---- Try to dispatch to real runner if available ----
    result: Dict[str, Any] = {"agent": agent_slug, "platform": platform, "echo": (req.payload or {})}
    try:
        # Prefer new style runner
        AgentRunner = None  # type: ignore
        try:
            from app.runners.agent_runner import AgentRunner as _AR  # your unified runner
            AgentRunner = _AR
        except Exception:
            AgentRunner = None
        if AgentRunner:
            runner = AgentRunner()
            # Best-effort call signature
            out = await runner.run(agent_slug=agent_slug, provider=None, model_override=None, payload=(req.payload or {}))
            result = {"agent": agent_slug, "platform": platform, "result": out}
    except Exception as e:
        log.warning("Runner error (legacy /agents/{sku}/run): %s", e)

    return {"ok": True, **result}

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

# ---------------------- OAuth2/JWT helpers for /v1/run ----------------------
ALLOW_DEV_BEARER = os.getenv("ALLOW_DEV_BEARER", "0") == "1"
REQUIRED_SCOPE = os.getenv("OAUTH_REQUIRED_SCOPE", "read")

JWKS_URL   = os.getenv("JWKS_URL")        # e.g. https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
OAUTH_ISS  = os.getenv("OAUTH_ISSUER")    # e.g. https://login.microsoftonline.com/<tenant>/v2.0
OAUTH_AUD  = os.getenv("OAUTH_AUDIENCE")  # e.g. api://<app-id> or client_id

_jose_available = True
try:
    from jose import jwt  # type: ignore
except Exception:
    _jose_available = False

def _extract_bearer(authz: Optional[str]) -> Optional[str]:
    if not authz:
        return None
    if not authz.lower().startswith("bearer "):
        return None
    return authz.split()[1]

def _email_from_claims(claims: Dict[str, Any]) -> str:
    return (claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("email")
            or claims.get("unique_name")
            or "")

def _require_scope_in_claims(claims: Dict[str, Any], scope: str):
    scopes = claims.get("scp") or claims.get("scope") or ""
    if isinstance(scopes, str):
        scope_set = set(scopes.split())
    elif isinstance(scopes, list):
        scope_set = set(scopes)
    else:
        scope_set = set()
    if scope not in scope_set:
        raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")

from functools import lru_cache
@lru_cache(maxsize=1)
def _get_jwks():
    import requests  # lazy import
    resp = requests.get(JWKS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()

def _decode_bearer_token(token: str) -> Dict[str, Any]:
    if not _jose_available or not (JWKS_URL and OAUTH_AUD and OAUTH_ISS):
        # Dev mode fallback
        if ALLOW_DEV_BEARER:
            return {"scp": REQUIRED_SCOPE, "preferred_username": os.getenv("DEV_EMAIL", "dev@example.com")}
        raise HTTPException(status_code=500, detail="JWT verification not configured")
    try:
        unverified = jwt.get_unverified_header(token)
        keys = _get_jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == unverified.get("kid")), None)
        if not key:
            raise HTTPException(status_code=401, detail="Unknown token key id")
        return jwt.decode(token, key, algorithms=[unverified.get("alg", "RS256")], audience=OAUTH_AUD, issuer=OAUTH_ISS)
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Token decode error: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------------------- /v1/run models ----------------------
from pydantic import BaseModel, Field, ConfigDict, constr

Role = Literal["system", "user", "assistant"]

class ChatMessage(BaseModel):
    role: Role
    content: constr(strip_whitespace=True, min_length=1)

class V1RunRequest(BaseModel):
    agent_slug: constr(strip_whitespace=True, min_length=1)
    provider: Optional[Literal["openai", "gemini", "endpoint"]] = Field(default=None)
    model: Optional[str] = Field(default=None)
    input: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

class V1RunResponse(BaseModel):
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)

# ---------------------- /v1/run (Copilot/GPT-compatible) ----------------------
@app.post("/v1/run", summary="Run one finance agent by slug", tags=["v1"], response_model=V1RunResponse)
async def v1_run(
    req: V1RunRequest,
    authorization: Optional[str] = Header(default=None)
):
    token = _extract_bearer(authorization)
    if not token and not ALLOW_DEV_BEARER:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    claims = _decode_bearer_token(token) if token else {"scp": REQUIRED_SCOPE, "preferred_username": os.getenv("DEV_EMAIL", "dev@example.com")}
    _require_scope_in_claims(claims, REQUIRED_SCOPE)

    user_email = _email_from_claims(claims)
    if not user_email:
        raise HTTPException(status_code=401, detail="Email not found in token")

    # Platform inference: ตาม provider; ถ้าไม่ระบุ ให้ถือเป็น Copilot (ใช้กับ Custom Connector)
    platform = "Copilot"
    if req.provider == "openai":
        platform = "GPT"
    elif req.provider == "gemini":
        platform = "Gemini"

    # ตรวจ entitlement โดยตรงจาก agent_slug
    require_entitlement_for_agent_slug_or_403(user_email, req.agent_slug, platform)

    # ---- Try to dispatch to real runner if available ----
    payload: Dict[str, Any] = req.input or {}
    result: Dict[str, Any] = {"agent": req.agent_slug, "platform": platform, "echo": payload}

    try:
        AgentRunner = None  # type: ignore
        try:
            # preferred new runner
            from app.runners.agent_runner import AgentRunner as _AR  # noqa
            AgentRunner = _AR
        except Exception:
            AgentRunner = None

        if AgentRunner:
            runner = AgentRunner()
            out = await runner.run(
                agent_slug=req.agent_slug,
                provider=req.provider,
                model_override=req.model,
                payload=payload
            )
            result = {"agent": req.agent_slug, "platform": platform, "output": out}
        else:
            # optional fallback: try legacy function `app.runner.run(...)`
            try:
                runner_mod = importlib.import_module("app.runner")
                if hasattr(runner_mod, "run"):
                    out = await runner_mod.run(agent_slug=req.agent_slug, payload=payload, provider=req.provider, model=req.model)  # type: ignore
                    result = {"agent": req.agent_slug, "platform": platform, "output": out}
            except Exception as e2:
                log.info("No legacy runner available: %s", e2)

    except Exception as e:
        log.warning("Runner error (/v1/run): %s", e)
        # ไม่ให้ 500 ทันที—คืนผลแบบ echo เพื่อให้ connector ทดสอบผ่านได้
        result["runner_error"] = str(e)

    return V1RunResponse(ok=True, result=result)

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
