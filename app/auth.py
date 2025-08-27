# app/auth.py
import os
from fastapi import Header, HTTPException

API_KEY = os.getenv("COPILOT_API_KEY")

async def require_api_key(x_api_key: str = Header(None)):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
