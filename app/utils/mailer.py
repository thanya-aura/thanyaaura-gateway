import os
import smtplib
from email.mime.text import MIMEText

def send_email(subject, body):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receivers = os.getenv("EMAIL_TO", "").split(",")

    if not receivers or receivers == [""]:
        raise ValueError("No recipients defined for email.")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(receivers)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, receivers, msg.as_string())
