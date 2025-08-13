from .provider_openai import OpenAIProvider
from .provider_dummy import DummyProvider

AGENT_SPECS = {
    "CFS": {"provider":"openai"},
    "CFP": {"provider":"openai"},
    "CFPR": {"provider":"openai"},
    "REVS": {"provider":"openai"},
    "REVP": {"provider":"openai"},
    "REVPR": {"provider":"openai"},
    "CAPEXS": {"provider":"openai"},
    "CAPEXP": {"provider":"openai"},
    "CAPEXPR": {"provider":"openai"},
    "FXS": {"provider":"openai"},
    "FXP": {"provider":"openai"},
    "FXPR": {"provider":"openai"},
    "COSTS": {"provider":"openai"},
    "COSTP": {"provider":"openai"},
    "COSTPR": {"provider":"openai"},
    "BUDS": {"provider":"openai"},
    "BUDP": {"provider":"openai"},
    "BUDPR": {"provider":"openai"},
    "REPS": {"provider":"openai"},
    "REPP": {"provider":"openai"},
    "REPPR": {"provider":"openai"},
    "VARS": {"provider":"openai"},
    "VARP": {"provider":"openai"},
    "VARPR": {"provider":"openai"},
    "MARS": {"provider":"openai"},
    "MARP": {"provider":"openai"},
    "MARPR": {"provider":"openai"},
    "FORS": {"provider":"openai"},
    "FORP": {"provider":"openai"},
    "FORPR": {"provider":"openai"},
    "DECS": {"provider":"openai"},
    "DECP": {"provider":"openai"},
    "DESPR": {"provider":"openai"},
}

class AgentRunner:
    def __init__(self, openai_api_key: str):
        self.providers = {
            "openai": OpenAIProvider(openai_api_key),
            "dummy":  DummyProvider(),
        }

    async def run(self, agent_slug: str, payload: dict) -> dict:
        spec = AGENT_SPECS.get(agent_slug)
        if not spec:
            raise ValueError(f"Unknown agent_slug '{agent_slug}'")
        provider = self.providers[spec["provider"]]
        return await provider.execute(spec, payload)
