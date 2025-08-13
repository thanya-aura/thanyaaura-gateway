from app.providers.provider_openai import OpenAIProvider
from app.providers.provider_gemini import GeminiProvider
from app.agents import AGENT_SPECS

class AgentRunner:
    def __init__(self):
        self.openai = OpenAIProvider()
        self.gemini = GeminiProvider()

    async def run(self, agent_slug: str, provider: str | None, messages: list | None, model_override: str | None = None):
        spec = AGENT_SPECS.get(agent_slug)
        if not spec:
            raise ValueError(f"Unknown agent_slug '{agent_slug}'")
        # default provider = first in agent's list
        use_provider = (provider or (spec.get("providers") or ["openai"])[0]).lower()
        if use_provider not in ("openai","gemini","endpoint"):
            raise ValueError(f"Unsupported provider '{use_provider}'")

        if use_provider == "openai":
            return await self.openai.chat(messages, model_override)
        elif use_provider == "gemini":
            return await self.gemini.chat(messages, model_override)
        else:
            # endpoint passthrough, require spec['endpoint']
            endpoint = (spec.get("endpoint") or "").strip()
            if not endpoint:
                raise ValueError(f"Agent '{agent_slug}' has no endpoint configured")
            # callers should post directly to their microservice path; here we just return info
            return {"proxy_hint":"call endpoint directly", "endpoint": endpoint, "agent": agent_slug}
