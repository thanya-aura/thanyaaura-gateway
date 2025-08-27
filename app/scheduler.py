# app/scheduler.py
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from app import db, email_sender

# ---------- logging ----------
log = logging.getLogger("thanyaaura.scheduler")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ---------- config ----------
TZ = ZoneInfo(os.getenv("APP_TZ", "Asia/Bangkok"))
CRON_HOUR = int(os.getenv("CRON_HOUR", "9"))        # default 09:00 local TH time
CRON_MINUTE = int(os.getenv("CRON_MINUTE", "0"))
MISFIRE_GRACE = int(os.getenv("MISFIRE_GRACE", "3600"))  # seconds; allow up to 60m delay
MAX_INSTANCES = int(os.getenv("MAX_INSTANCES", "1"))      # avoid double sends
RUN_ON_DEPLOY = os.getenv("RUN_ON_DEPLOY", "").lower() in {"1", "true", "yes"}

def send_daily_emails():
    """
    Run the daily email checks/sends (Day 1/10/23 trial flow).
    Safe to run repeatedly; handles empty user sets without error.
    """
    now_local = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    log.info("Starting daily email job at %s", now_local)

    try:
        # Optional DB bootstrap (no-op if stubbed)
        db.ensure_permanent_admin_user()
    except Exception as e:
        log.warning("ensure_permanent_admin_user skipped: %s", e)

    total_sent = total_failed = 0
    for day in (1, 10, 23):
        users = db.get_trial_users_by_day(day_offset=day) or []
        if not users:
            log.info("No trial users for Day %s.", day)
            continue

        sent = failed = 0
        for user in users:
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

        log.info("Day %s emails: sent=%d failed=%d", day, sent, failed)
        total_sent += sent
        total_failed += failed

    log.info("Daily email job finished. total_sent=%d total_failed=%d", total_sent, total_failed)

def _add_job(scheduler: BlockingScheduler):
    trigger = CronTrigger(hour=CRON_HOUR, minute=CRON_MINUTE, timezone=TZ)
    scheduler.add_job(
        send_daily_emails,
        trigger,
        id="daily_emails_9am_th",
        replace_existing=True,
        max_instances=MAX_INSTANCES,   # never overlap runs
        coalesce=True,                 # if missed, run only once (no backlog)
        misfire_grace_time=MISFIRE_GRACE,
    )

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
        scheduler.start()  # keep the worker alive (prevents Render from restarting it)
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
