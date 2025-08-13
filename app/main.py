from fastapi import FastAPI, Request, HTTPException
# Known SKUs used by checkout slugs (derive from fulfillment[url] without needing query params)
KNOWN_SKUS = {
    "module-0-cfs","module-0-cfr","module-0-cfpr",
    "module-0-revs","module-0-revp","module-0-revpr",
    "module-0-capexs","module-0-capexp","module-0-capexpr",
    "module-0-fxs","module-0-fxp","module-0-fxpr",
    "module-0-costs","module-0-costp","module-0-costpr",
    "module-0-buds","module-0-budp","module-0-budpr",
    "module-0-reps","module-0-repp","module-0-reppr",
    "module-0-vars","module-0-varp","module-0-varpr",
    "module-0-mars","module-0-marp","module-0-marpr",
    "module-0-fors","module-0-forp","module-0-forpr",
    "module-0-decs","module-0-decp","module-0-decpr",
}
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

def pick_sku_from(data: dict) -> str | None:
    """Try multiple shapes and also derive from fulfillment[url] slug."""
    # direct keys and passthrough forms
    for k in ("sku","product_sku","passthrough_sku","passthrough[sku]","passthrough.sku"):
        v = data.get(k)
        if v:
            return v
    p = data.get("passthrough")
    if isinstance(p, dict):
        v = p.get("sku")
        if v:
            return v

    # derive from fulfillment url
    fu = data.get("fulfillment[url]")
    if not fu:
        ful = data.get("fulfillment")
        if isinstance(ful, dict):
            fu = ful.get("url")
    if fu:
        try:
            from urllib.parse import urlparse as _urlparse
            slug = _urlparse(fu).path.strip("/").split("/")[0]
            if slug in KNOWN_SKUS:
                return slug
        except Exception:
            pass
    return None
