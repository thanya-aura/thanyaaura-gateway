# Thanyaaura Gateway (patch)
Start Command:
```
gunicorn app.main:app -k uvicorn.workers.UvicornWorker
```

ENV:
- DATABASE_URL
- THRIVECART_SECRET
- LOG_LEVEL=info

Webhook URL:
- https://<your-domain>/billing/thrivecart
