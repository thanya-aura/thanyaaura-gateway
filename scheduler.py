import logging
import sys
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logging.info("Scheduler started...")

scheduler = BlockingScheduler()

# Example scheduled job every 1 minute
@scheduler.scheduled_job('interval', minutes=1)
def scheduled_task():
    logging.info("Running scheduled task...")

if __name__ == "__main__":
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")
