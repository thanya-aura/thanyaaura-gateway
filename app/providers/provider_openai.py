import os, httpx
from app.config import OPENAI_API_KEY, MODEL_DEFAULT_OPENAI

class OpenAIProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or OPENAI_API_KEY

    async def chat(self, messages: list, model: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": model or MODEL_DEFAULT_OPENAI, "messages": messages or [{"role":"user","content":"Hello"}]}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions", json=body, headers=headers)
            r.raise_for_status()
            return r.json()
