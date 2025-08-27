# app/models.py
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, EmailStr

class RunAgentRequest(BaseModel):
    """
    Request body สำหรับ /agents/{sku}/run
    - email: ใช้ตรวจสิทธิ์ (entitlement) ของผู้ใช้
    - payload: ข้อมูลอินพุตเฉพาะเอเจนต์ (ใส่หรือไม่ใส่ก็ได้)
    """
    email: EmailStr = Field(..., description="End-user email (UPN) used for entitlement check")
    payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Agent-specific inputs"
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"email": "alice@company.com",
                 "payload": {"month": "2025-08", "currency": "USD"}}
            ]
        },
    )

__all__ = ["RunAgentRequest"]
