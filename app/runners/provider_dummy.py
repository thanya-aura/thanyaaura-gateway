class DummyProvider:
    async def execute(self, spec: dict, payload: dict) -> dict:
        return {"mock": True, "echo": payload, "agent_spec": spec}
