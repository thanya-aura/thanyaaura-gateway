from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.utils.mailer import send_email
import time
from pytz import timezone

def job_check_membership():
    subject = "⚠️ Membership Expiry Alert"
    body = "Hello, your membership is about to expire. Please renew to continue service."
    send_email(subject, body)

def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run job_check_membership once a day at 21:00 TH time (Asia/Bangkok)
    scheduler.add_job(
        job_check_membership,
        CronTrigger(hour=9, minute=0, timezone=timezone("Asia/Bangkok"))
    )
    scheduler.start()
    return scheduler

if __name__ == "__main__":
    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
