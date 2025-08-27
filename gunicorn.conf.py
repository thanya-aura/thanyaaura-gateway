# gunicorn.conf.py
import os

# ให้ Gunicorn bind ไปที่พอร์ตที่ Render กำหนด (อ่านจาก env PORT)
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# ใช้ Uvicorn worker ตามเดิม
worker_class = "uvicorn.workers.UvicornWorker"

# ตั้งค่าทั่วไป (ปรับได้ผ่าน env ถ้าต้องการ)
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
