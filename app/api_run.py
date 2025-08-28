# app/api_run.py
from fastapi import APIRouter, Header, HTTPException, Body, Request
from pydantic import BaseModel, Field, constr, validator
from typing import Optional, Literal, List, Dict, Any
import httpx, os

# ===== Models =====
Role = Literal["system", "user", "assistant"]

class ChatMessage(BaseModel):
    role: Role
    content: constr(strip_whitespace=True, min_length=1)

class InputPayload(BaseModel):
    messages: Optional[List[ChatMessage]] = Field(default=None)
    # รับ key อื่น ๆ เพิ่มได้ (additionalProperties)
    __root__: Optional[Dict[str, Any]] = None

class RunRequest(BaseModel):
    agent_slug: constr(strip_whitespace=True, min_length=1)
    provider: Optional[Literal["openai", "gemini", "endpoint"]] = None
    model: Optional[str] = None
    input: Dict[str, Any]  # ยอมรับ object อิสระ โดยอย่างน้อยควรมี messages

class RunResponse(BaseModel):
    ok: bool = True
    result: Dict[str, Any] = {}

router = APIRouter()

# ===== Security / OAuth2 helpers =====
from jose import jwt
import requests

JWKS_URL = os.getenv("JWKS_URL")              # เช่น https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
AUDIENCE  = os.getenv("OAUTH_AUDIENCE")       # client_id / api://<app-id>
ISSUER    = os.getenv("OAUTH_ISSUER")         # https://login.microsoftonline.com/<tenant>/v2.0
REQUIRED_SCOPE = "read"

from functools import lru_cache
@lru_cache(maxsize=1)
def _jwks():
    if not JWKS_URL:
        return None
    return requests.get(JWKS_URL, timeout=10).json()

def _decode_bearer(token: str) -> dict:
    if not JWKS_URL:
        # dev mode (ไม่ควรใช้ production)
        return {"scp": "read", "preferred_username": "dev@example.com"}
    from jose.utils import base64url_decode
    unverified = jwt.get_unverified_header(token)
    keys = _jwks().get("keys", [])
    key = next((k for k in keys if k.get("kid") == unverified.get("kid")), None)
    if not key:
        raise HTTPException(status_code=401, detail="Unknown token key id")
    return jwt.decode(token, key, algorithms=[unverified.get("alg", "RS256")], audience=AUDIENCE, issuer=ISSUER)

def _require_scope(claims: dict, scope: str):
    scopes = claims.get("scp") or claims.get("scope") or ""
    scopes_set = set(scopes.split()) if isinstance(scopes, str) else set(scopes)
    if scope not in scopes_set:
        raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")

def _email_from_claims(claims: dict) -> str:
    return claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""

# ===== Entitlement check (เชื่อมกับโมดูลเดิมของ gateway) =====
from app.enterprise_access import check_access  # สมมุติว่ามีฟังก์ชันลักษณะนี้อยู่แล้ว

def _assert_entitled(email: str, agent_slug: str):
    allowed = check_access(email=email, agent_slug=agent_slug)
    if not allowed:
        raise HTTPException(status_code=403, detail=f"Not entitled for agent {agent_slug}")

# ===== Agent registry/runner =====
from app.runners.agent_runner import AgentRunner  # ตัววิ่งรวม provider ของคุณ
runner = AgentRunner()

@router.post("/v1/run", response_model=RunResponse)
async def run_agent(
    req: RunRequest,
    authorization: Optional[str] = Header(default=None),
    request: Request = None
):
    # 1) OAuth2 Bearer
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split()[1]
    claims = _decode_bearer(token)
    _require_scope(claims, REQUIRED_SCOPE)

    # 2) Entitlement (ผูกสิทธิ์กับอีเมลจากโทเค็น)
    email = _email_from_claims(claims)
    if not email:
        raise HTTPException(status_code=401, detail="Email not found in token")
    _assert_entitled(email, req.agent_slug)

    # 3) Dispatch ไปยังตัว agent ตาม provider/model/messages
    try:
        result = await runner.run(
            agent_slug=req.agent_slug,
            provider=req.provider,           # ถ้า None ให้ runner เลือก default
            model_override=req.model,
            payload=req.input                # ภายใน runner รองรับ 'messages' และ keys อื่น ๆ
        )
    except Exception as e:
        # log error ที่นี่ตามระบบของคุณ
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    return RunResponse(ok=True, result=result)
