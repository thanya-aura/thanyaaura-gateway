import os, httpx
from app.config import GEMINI_API_KEY, MODEL_DEFAULT_GEMINI

class GeminiProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or GEMINI_API_KEY

    async def chat(self, messages: list, model: str | None = None) -> dict:
        # Convert OpenAI-style messages to Gemini's contents
        # Gemini expects: contents: [{role:"user"/"model", parts:[{text:"..."}]}]
        contents = []
        for m in messages or [{"role":"user","content":"Hello"}]:
            role = "user" if m.get("role") != "assistant" else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content","")}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or MODEL_DEFAULT_GEMINI}:generateContent?key={self.api_key}"
        payload = {"contents": contents}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
