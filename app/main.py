from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.runner import AgentRunner

app = FastAPI(title="Thanayaura Dual-Provider Gateway", version="2.0.0")
runner = AgentRunner()

class ChatMessage(BaseModel):
    role: str
    content: str

class RunReq(BaseModel):
    agent_slug: str
    provider: Optional[str] = None    # "openai" | "gemini" | "endpoint"
    model: Optional[str] = None       # override per-call model
    input: Dict[str, Any] = {}        # expects {"messages":[...]}

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/v1/run")
async def run(req: RunReq):
    try:
        messages = req.input.get("messages", [])
        result = await runner.run(req.agent_slug, req.provider, messages, req.model)
        return {"ok": True, "result": result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Internal error: {e}")
