import re
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from app.agents import get_agent_slug_from_sku

app = FastAPI()

def derive_sku(data: dict) -> str | None:
    sku = data.get("sku") or data.get("passthrough[sku]")
    if sku:
        return sku.strip().lower()
    f_url = data.get("fulfillment[url]") or data.get("fulfillment") or data.get("fulfillment_url")
    if f_url:
        try:
            path = urlparse(f_url).path.lower()
            m = re.search(r"/module-0-([a-z0-9_]+)(?:/|$)", path)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None

@app.post("/billing/thrivecart")
async def billing_thrivecart(request: Request):
    form = await request.form()
    data = dict(form)
    sku = derive_sku(data)
    if not sku:
        raise HTTPException(status_code=400, detail="Missing SKU")
    agent_slug = get_agent_slug_from_sku(sku)
    if not agent_slug:
        raise HTTPException(status_code=400, detail=f"Unknown SKU: {sku}")
    return {"ok": True, "agent_slug": agent_slug}
