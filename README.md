# Thanayaura Gateway (Dual Provider: OpenAI GPT-5 + Gemini)

## Environment
- `OPENAI_API_KEY` (required for OpenAI)
- `GEMINI_API_KEY` (required for Gemini)
- `MODEL_DEFAULT_OPENAI` (default `gpt-5`)
- `MODEL_DEFAULT_GEMINI` (default `gemini-2.0-pro`)

## Run
```
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

## Endpoint
- `GET /healthz`
- `POST /v1/run`
  ```json
  {
    "agent_slug": "CFS",
    "provider": "openai",
    "model": "gpt-5",
    "input": {
      "messages": [{"role":"user","content":"Ping"}]
    }
  }
  ```
