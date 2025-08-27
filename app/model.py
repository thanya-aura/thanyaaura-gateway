# app/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class RunAgentRequest(BaseModel):
    email: str = Field(..., description="End-user email (UPN) to check entitlements")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="Agent-specific inputs")
