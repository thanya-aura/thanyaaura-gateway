import os
import logging
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from app import db, email_sender

log = logging.getLogger("thanyaaura.scheduler")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# Use Thailand time by default; allow override via APP_TZ
TZ = ZoneInfo(os.getenv("APP_TZ", "Asia/Bangkok"))

def send_daily_emails():
    """
    Run the daily email checks/sends (Day 1/10/23 trial flow).
    Safe to run repeatedly; handles empty user sets without error.
    """
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

if __name__ == "__main__":
    # Optional: run immediately on deploy for testing if RUN_ON_DEPLOY=true
    if os.getenv("RUN_ON_DEPLOY", "").lower() in {"1", "true", "yes"}:
        log.info("RUN_ON_DEPLOY detected — running once now before scheduling.")
        try:
            send_daily_emails()
        except Exception as e:
            log.error("Immediate run failed: %s", e)

    scheduler = BlockingScheduler(timezone=TZ)

    # Fire once per day at 09:00 Thailand time
    trigger = CronTrigger(hour=9, minute=0, timezone=TZ)
    scheduler.add_job(send_daily_emails, trigger, id="daily_emails_9am_th", replace_existing=True)

    log.info("Scheduler started. Job runs daily at 09:00 %s (UTC offset varies with TZ).", TZ.key)
    try:
        scheduler.start()  # Keep the worker process alive (prevents Render from restarting it)
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
