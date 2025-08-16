from apscheduler.schedulers.background import BackgroundScheduler
from app.db import get_trial_users_by_day
import time

def job_check_trials():
    users = get_trial_users_by_day(0)
    if users:
        print(f"[Scheduler] Found {len(users)} trial users today: {users}")
    else:
        print("[Scheduler] No trial users found today.")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(job_check_trials, 'interval', minutes=1)
    scheduler.start()

    print("[Scheduler] Background worker started.")

    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
