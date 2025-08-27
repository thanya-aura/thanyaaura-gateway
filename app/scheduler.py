import logging
from app.db import get_trial_users_by_day
from app.email_sender import send_platform_email

log = logging.getLogger("thanyaaura.scheduler")
logging.basicConfig(level=logging.INFO)


def run_day_emails(day_offset: int):
    """
    Send platform-aware emails for users at a specific trial day offset.
    Example: 1 -> Day 1 welcome, 10 -> Day 10 case study, 23 -> Day 23 executive insights.
    """
    users = get_trial_users_by_day(day_offset)

    if not users:
        log.info(f"No users found for day_offset={day_offset}")
        return

    log.info(f"Sending emails for day_offset={day_offset}, users={len(users)}")

    for u in users:
        try:
            ok = send_platform_email(u, day_offset=day_offset)
            if ok:
                log.info(f"Email sent successfully → {u['user_email']} (platform={u.get('platform')})")
            else:
                log.warning(f"Email failed → {u['user_email']} (platform={u.get('platform')})")
        except Exception as ex:
            log.error(f"Error sending email to {u['user_email']}: {ex}", exc_info=True)


def run_all():
    """
    Convenience runner: checks Day 1, 10, 23 in sequence.
    Can be hooked to a daily cron job.
    """
    for offset in (1, 10, 23):
        run_day_emails(offset)


if __name__ == "__main__":
    # When run directly (e.g. python scheduler.py), send all 3 day emails
    run_all()
