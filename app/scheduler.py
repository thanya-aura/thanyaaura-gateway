from apscheduler.schedulers.background import BackgroundScheduler
import time

def job_check_users():
    print("✅ Scheduler is working and job executed.")

def job_send_test_email():
    # simulate sending an email (replace with your actual email logic)
    print("📧 Test email function triggered.")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(job_check_users, 'interval', minutes=1)
    scheduler.add_job(job_send_test_email, 'interval', minutes=2)
    scheduler.start()
    print("🚀 Scheduler started. Jobs are running...")

    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("🛑 Scheduler stopped.")
