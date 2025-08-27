# app/auth.py
import os
from fastapi import Header, HTTPException

def require_api_key(x_api_key: str = Header(None)):
    """ตรวจ API key แบบง่าย ๆ: ถ้าไม่ตั้งค่า API_KEY ใน env จะปล่อยผ่าน"""
    expected = os.getenv("API_KEY")
    if not expected:
        return True
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

