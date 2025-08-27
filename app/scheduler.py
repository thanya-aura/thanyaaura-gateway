import logging
from app import db, email_sender

log = logging.getLogger("thanyaaura.scheduler")

def run_scheduled_emails():
    # Trial offsets we support
    days = [1, 10, 23]

    for day in days:
        users = db.get_trial_users_by_day(day_offset=day)
        if not users:
            # ✅ Changed: don't make it look like a problem
            log.info(f"✅ Scheduler ran: No trial users for Day {day} (this is normal if none signed up {day} days ago).")
            continue

        log.info(f"Found {len(users)} users for Day {day}")
        for user in users:
            email_sender.send_trial_email(
                day,
                user,
                agent_name="Finance AI Agent",
                links={
                    "gpt_link": "https://chat.openai.com/",
                    "gemini_link": "https://gemini.google.com/",
                    "copilot_link": "https://copilot.microsoft.com/",
                    "upgrade_link": "https://your-upgrade-link.com",
                },
            )

if __name__ == "__main__":
    run_scheduled_emails()
