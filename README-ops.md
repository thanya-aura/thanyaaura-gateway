# Thanyaaura Gateway — patched bundle

Included:

- `app/main.py` — warns when **fallback** map is used and can be disabled via env `AGENT_FALLBACK_ENABLED=0`.
- `scripts/check-db.ps1` — one-click Postgres check (with your password embedded as requested).
- `scripts/smoke-webhook.ps1` — quick webhook smoke tests.

## Turn off fallback (recommended once `app/agents.py` is ready)
Set environment variable on Render:
```
AGENT_FALLBACK_ENABLED=0
```
Now only `app.agents.get_agent_slug_from_sku()` and its table will be used. Any unknown SKU will 400.

## Run checks on Windows PowerShell
```powershell
C:\> PowerShell -ExecutionPolicy Bypass -File .\scripts\check-db.ps1
C:\> PowerShell -ExecutionPolicy Bypass -File .\scripts\smoke-webhook.ps1 -Gateway https://thanyaaura-gateway-1.onrender.com -Email buyer@example.com
```
