from apscheduler.schedulers.background import BackgroundScheduler
from app.db import get_trial_users_by_day
from app.email_sender import send_email

def job_send_emails():
    # Example for Day 1-7
    users_day7 = get_trial_users_by_day(23)  # If trial is 30 days, 30-7 = 23 days left
    for user in users_day7:
        name, email = user
        send_email(email, "Welcome to Your Free Trial", f"<h1>Hi {name}</h1><p>Welcome!</p>")

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(job_send_emails, 'interval', days=1)
    scheduler.start()
