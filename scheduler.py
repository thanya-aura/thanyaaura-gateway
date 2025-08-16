from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.utils.mailer import send_email

def job_check_membership():
    subject = "⚠️ Membership Expiry Alert"
    body = "Hello, your membership is about to expire. Please renew to continue service."
    send_email(subject, body)

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
    # ✅ Run once a day at 9:00 AM
    scheduler.add_job(
        job_check_membership,
        trigger=CronTrigger(hour=9, minute=0)
    )
    scheduler.start()

if __name__ == "__main__":
    start_scheduler()
