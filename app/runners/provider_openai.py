import os, httpx
from app.config import MODEL_DEFAULT

class OpenAIProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY","")

    async def execute(self, spec: dict, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}","Content-Type":"application/json"}
        model = spec.get("model", MODEL_DEFAULT)  # default to GPT-5 unless overridden per agent
        body = {
            "model": model,
            "messages": payload.get("messages", [{"role":"user","content":"Hello from Gateway"}])
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions", json=body, headers=headers)
            r.raise_for_status()
            return r.json()
