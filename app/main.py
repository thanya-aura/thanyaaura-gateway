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
