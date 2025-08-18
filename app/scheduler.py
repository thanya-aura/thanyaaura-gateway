from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.utils.mailer import send_email
import time

def job_check_membership():
    subject = "⚠️ Membership Expiry Alert"
    body = "Hello, your membership is about to expire. Please renew to continue service."
    send_email(subject, body)

def job_test():
    # Simple test job to confirm scheduler is running on Render
    print("✅ Test job executed")

def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run membership check every day at 9:00
    scheduler.add_job(job_check_membership, CronTrigger(hour=9, minute=0))
    # Run test job every 1 minute (for Render log check)
    scheduler.add_job(job_test, 'interval', minutes=1)
    scheduler.start()
    return scheduler

if __name__ == "__main__":
    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
