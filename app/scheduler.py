# app/scheduler.py

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from app import db, email_sender

# ---------- logging ----------
def _env_log_level(default: str = "INFO") -> int:
    """Normalize LOG_LEVEL env (e.g., 'info', 'INFO', '20') to a valid logging level."""
    lvl = str(os.getenv("LOG_LEVEL", default)).strip()
    if lvl.isdigit():
        return int(lvl)
    return getattr(logging, lvl.upper(), logging.INFO)

logging.basicConfig(
    level=_env_log_level(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("thanyaaura.scheduler")


# ---------- config helpers ----------
def _env_int(name: str, default: int, _min: int | None = None, _max: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        val = int(str(raw).strip())
    except Exception:
        return default
    if _min is not None and val < _min:
        return default
    if _max is not None and val > _max:
        return default
    return val


# ---------- config ----------
TZ = ZoneInfo(os.getenv("APP_TZ", "Asia/Bangkok"))
CRON_HOUR = _env_int("CRON_HOUR", 9, 0, 23)                 # default 09:00 TH time
CRON_MINUTE = _env_int("CRON_MINUTE", 0, 0, 59)
MISFIRE_GRACE = _env_int("MISFIRE_GRACE", 3600, 0, 24 * 3600)  # seconds
MAX_INSTANCES = _env_int("MAX_INSTANCES", 1, 1, 32)            # avoid overlap/double sends
JOB_ID = os.getenv("JOB_ID", "daily_emails_9am_th")
RUN_ON_DEPLOY = os.getenv("RUN_ON_DEPLOY", "").lower() in {"1", "true", "yes"}


# ---------- job ----------
def send_daily_emails():
    """
    Run the daily email checks/sends (Day 1/10/23 trial flow).
    Safe to run repeatedly; handles empty user sets without error.
    """
    now_local = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    log.info("Starting daily email job at %s", now_local)

    try:
        # Optional DB bootstrap (no-op if already present)
        db.ensure_permanent_admin_user()
    except Exception as e:
        log.warning("ensure_permanent_admin_user skipped: %s", e)

    total_sent = total_failed = 0
    for day in (1, 10, 23):
        try:
            users = db.get_trial_users_by_day(day_offset=day) or []
        except Exception as e:
            users = []
            log.error("DB error fetching trial users for Day %s: %s", day, e)

        if not users:
            log.info("No trial users for Day %s.", day)
            continue

        sent = failed = 0
        for user in users:
            try:
                ok = email_sender.send_trial_email(
                    day,
                    user,
                    agent_name="Finance AI Agent",
                    links={
                        "gpt_link": os.getenv("LINK_GPT", "https://chat.openai.com/"),
                        "gemini_link": os.getenv("LINK_GEMINI", "https://gemini.google.com/"),
                        "copilot_link": os.getenv("LINK_COPILOT", "https://copilot.microsoft.com/"),
                        "upgrade_link": os.getenv("LINK_UPGRADE", "https://example.com/upgrade"),
                    },
                )
                if ok:
                    sent += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                log.error("Send error (Day %s) to %s: %s", day, user.get("user_email"), e)

        log.info("Day %s emails: sent=%d failed=%d", day, sent, failed)
        total_sent += sent
        total_failed += failed

    log.info("Daily email job finished. total_sent=%d total_failed=%d", total_sent, total_failed)


def _add_job(scheduler: BlockingScheduler):
    trigger = CronTrigger(hour=CRON_HOUR, minute=CRON_MINUTE, timezone=TZ)
    scheduler.add_job(
        send_daily_emails,
        trigger,
        id=JOB_ID,
        replace_existing=True,
        max_instances=MAX_INSTANCES,   # never overlap runs
        coalesce=True,                 # if multiple runs missed, run only once
        misfire_grace_time=MISFIRE_GRACE,
    )


# ---------- entrypoint ----------
if __name__ == "__main__":
    # Optional one-off run on deploy for testing
    if RUN_ON_DEPLOY:
        log.info("RUN_ON_DEPLOY=true — running once now before scheduling.")
        try:
            send_daily_emails()
        except Exception as e:
            log.error("Immediate run failed: %s", e)

    scheduler = BlockingScheduler(timezone=TZ)
    _add_job(scheduler)

    now_local = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    log.info(
        "Scheduler started at %s. Job runs daily at %02d:%02d %s.",
        now_local, CRON_HOUR, CRON_MINUTE, TZ.key
    )

    try:
        scheduler.start()  # keep the worker process alive
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
