# app/limits.py
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.plans import PLAN_BY_CODE
from app.agent_tiers import classify_agent_tier

log = logging.getLogger("thanyaaura.gateway.limits")

# -------- Feature flags (via env) --------
import os
# อนุญาตให้ "degrade" (ไม่บล็อก) เมื่อ DB method ยังไม่พร้อมระหว่างช่วง transition
LIMITS_DEGRADE_OK = os.getenv("LIMITS_DEGRADE_OK", "1") == "1"
# บังคับให้ต้องมี X-API-Key เสมอ
LIMITS_REQUIRE_API_KEY = os.getenv("LIMITS_REQUIRE_API_KEY", "1") == "1"


def _yyyymm_now() -> str:
    dt = datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


async def _db_safe_call(db: Any, fn_name: str, *args, default=None, **kwargs):
    """
    เรียกเมธอดใน app.db แบบปลอดภัย + รองรับทั้ง sync/async:
      - ถ้าไม่มีเมธอด -> log.warn และคืน default
      - ถ้าเกิด error     -> log.warn และคืน default
    """
    try:
        fn = getattr(db, fn_name, None)
        if not callable(fn):
            log.warning("DB method missing: %s", fn_name)
            return default
        # ตรวจว่าเป็น coroutine หรือไม่
        if getattr(fn, "__await__", None) is not None:
            # async function
            return await fn(*args, **kwargs)
        # sync function → รันใน threadpool
        return await run_in_threadpool(fn, *args, **kwargs)
    except Exception as e:
        log.warning("DB method %s error: %s", fn_name, e)
        return default


def _fail_or_degrade(detail: str):
    """
    ถ้า LIMITS_DEGRADE_OK = 1 → แค่ log warning แต่ปล่อยผ่าน (ไม่บล็อก)
    ถ้า LIMITS_DEGRADE_OK = 0 → บล็อกด้วย HTTP 500/403 ตามที่กำหนดเรียกใช้
    """
    if LIMITS_DEGRADE_OK:
        log.warning("Degrade mode: %s -- allowing temporarily.", detail)
        return
    # ผู้เรียกจะ raise เอง (อย่าระบุ status ที่นี่เพื่อความยืดหยุ่น)
    raise RuntimeError(detail)


def _get_api_key_from_request(request: Request) -> Optional[str]:
    # หลัก: อ่านจาก X-API-Key; สำรอง: Authorization: ApiKey <key>
    key = request.headers.get("X-API-Key")
    if key:
        return key
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("apikey "):
        return auth.split(" ", 1)[1].strip() or None
    return None


async def _choose_usage_bucket(db, tenant_id: int, sub: dict) -> str:
    """
    คืน key ของ usage bucket รายเดือน
    - ถ้ามี DB helper เฉพาะ (get_usage_bucket_key) ให้ใช้
    - ไม่มีก็ fallback เป็น YYYY-MM (UTC)
    หมายเหตุ: ถ้าอยาก align กับวัน renew (renew_day) จริง ๆ ให้ทำ helper ใน DB แล้วเมธอดนี้จะเรียกใช้
    """
    # ลองใช้ helper จาก DB ถ้ามี
    key = await _db_safe_call(db, "get_usage_bucket_key", tenant_id, sub, default=None)
    if isinstance(key, str) and key:
        return key
    # fallback: ปฏิทินรายเดือนแบบ UTC
    return _yyyymm_now()


async def require_tenant_and_quota(request: Request, agent_slug: str):
    """
    ใช้ร่วมกับ Thin endpoint (/v1/run):
      - ตรวจ API key ราย tenant (header: X-API-Key หรือ Authorization: ApiKey <key>)
      - โหลด subscription (plan_code, monthly_quota, extra_quota_balance, renew_day?)
      - ตรวจสิทธิ์ตาม tier ของ agent โดยเทียบกับ PLAN_BY_CODE[plan_code].allowed_tiers
      - กันนับซ้ำด้วย X-Idempotency-Key
      - หัก quota 1 call (optimistic)
    ถ้า DB เมธอดที่ต้องใช้ยังไม่มี -> (ขึ้นกับ LIMITS_DEGRADE_OK)
    """
    # 0) รับ API key
    api_key = _get_api_key_from_request(request)
    if not api_key:
        if LIMITS_REQUIRE_API_KEY:
            raise HTTPException(status_code=401, detail="Missing API key")
        else:
            # ไม่บังคับ API key (dev/preview) → degrade
            _fail_or_degrade("API key missing but LIMITS_REQUIRE_API_KEY=0")
            request.state.tenant_id = None
            request.state.plan_code = None
            request.state.quota_checked = False
            return

    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    # 1) db module
    db = getattr(request.app.state, "db", None)
    if not db:
        _fail_or_degrade("app.state.db is not ready")
        request.state.tenant_id = None
        request.state.plan_code = None
        request.state.quota_checked = False
        return

    # 2) หา tenant จาก api_key hash
    tenant = await _db_safe_call(db, "get_tenant_by_api_key_hash", key_hash, default=None)
    if tenant is None:
        _fail_or_degrade("tenant not found or DB function missing")
        request.state.tenant_id = None
        request.state.plan_code = None
        request.state.quota_checked = False
        return

    if tenant.get("status") not in (None, "active"):
        raise HTTPException(status_code=403, detail="Subscription inactive")

    tenant_id = tenant.get("id") or tenant.get("tenant_id")

    # 3) โหลด subscription ปัจจุบันของ tenant
    sub = await _db_safe_call(db, "get_subscription_by_tenant_id", tenant_id, default=None)
    if sub is None:
        _fail_or_degrade("subscription missing")
        request.state.tenant_id = tenant_id
        request.state.plan_code = None
        request.state.quota_checked = False
        return

    if sub.get("status") not in (None, "active"):
        raise HTTPException(status_code=403, detail="Subscription not active")

    plan_code = sub.get("plan_code")
    plan = PLAN_BY_CODE.get(plan_code)
    if not plan:
        _fail_or_degrade(f"unknown plan_code={plan_code}")
        request.state.tenant_id = tenant_id
        request.state.plan_code = plan_code
        request.state.quota_checked = False
        return

    # 4) ตรวจสิทธิ์ตาม tier ของ agent
    try:
        tier = classify_agent_tier(agent_slug)
    except Exception as e:
        log.warning("classify_agent_tier error on %r: %s", agent_slug, e)
        raise HTTPException(status_code=400, detail="Invalid agent slug")

    if tier not in plan.allowed_tiers:
        raise HTTPException(status_code=403, detail=f"Plan does not allow {tier} agents")

    # 5) ตรวจโควตรายเดือน + กันนับซ้ำ
    bucket_key = await _choose_usage_bucket(db, int(tenant_id), sub)

    idem = request.headers.get("X-Idempotency-Key")
    # ถ้า idempotency key เคยใช้แล้ว -> ผ่านโดยไม่หัก quota ซ้ำ
    seen = await _db_safe_call(db, "seen_idempotency", tenant_id, idem, default=False) if idem else False
    if seen:
        request.state.tenant_id = tenant_id
        request.state.plan_code = plan_code
        request.state.quota_checked = False
        return

    # สร้าง bucket ถ้ายังไม่มี
    await _db_safe_call(db, "ensure_usage_bucket", tenant_id, bucket_key, default=True)

    used = await _db_safe_call(db, "get_calls_used", tenant_id, bucket_key, default=0)
    base_quota = int(sub.get("monthly_quota", 0) or 0)
    extra_quota = int(sub.get("extra_quota_balance", 0) or 0)
    limit = base_quota + extra_quota

    # ถ้า DB ไม่พร้อม/คืน None → degrade (ตาม flag)
    if used is None:
        _fail_or_degrade("get_calls_used returned None")
        request.state.tenant_id = tenant_id
        request.state.plan_code = plan_code
        request.state.quota_checked = False
        return

    if limit > 0 and used >= limit:
        raise HTTPException(status_code=403, detail="Monthly quota exceeded")

    # จอง 1 call (optimistic)
    ok = await _db_safe_call(db, "increment_calls_used", tenant_id, bucket_key, 1, default=True)
    if not ok:
        # กัน race: ถ้าเพิ่มไม่ได้ให้ถือว่า quota เต็ม
        raise HTTPException(status_code=403, detail="Monthly quota exceeded")

    # ทำเครื่องหมาย idempotency key
    if idem:
        await _db_safe_call(db, "write_idempotency", tenant_id, idem, default=True)

    # expose state ให้ปลายทาง (ใช้แสดงผล/ดีบัก)
    request.state.tenant_id = tenant_id
    request.state.plan_code = plan_code
    request.state.quota_checked = True
