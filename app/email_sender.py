import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "your_email@example.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "your_password")  # must be set in Render env


def send_email(recipient: str, subject: str, html_content: str) -> bool:
    """
    Send an email with HTML content.
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = recipient
    msg["Subject"] = subject

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, recipient, msg.as_string())
        return True
    except Exception as ex:
        print(f"Email send error: {ex}")
        return False


def send_platform_email(user: dict, day_offset: int) -> bool:
    """
    Send a platform-specific onboarding email.
    user: dict containing {"user_email": ..., "platform": ...}
    day_offset: int (0=Day 1, 14=Day 14, 27=Day 27)
    """
    email = user.get("user_email")
    platform = (user.get("platform") or "GPT").strip()

    # Choose subject & content by platform
    if platform == "Gemini":
        subject = f"[Day {day_offset}] Welcome to Gemini Finance Agent!"
        html = f"""
        <p>Hello,</p>
        <p>Thanks for joining via <b>Gemini</b>. Today is Day {day_offset} of your journey.</p>
        <p>Here’s how to make the most of your Gemini integration with Finance Agent.</p>
        """
    elif platform.startswith("Copilot"):
        subject = f"[Day {day_offset}] Welcome to Microsoft Copilot Finance Agent!"
        html = f"""
        <p>Hello,</p>
        <p>Welcome aboard <b>Microsoft Copilot</b> Finance Agent. Today is Day {day_offset} of your subscription.</p>
        <p>Your enterprise-level insights are ready to explore.</p>
        """
    else:
        subject = f"[Day {day_offset}] Welcome to GPT Finance Agent!"
        html = f"""
        <p>Hello,</p>
        <p>Thanks for signing up through <b>GPT</b>. This is Day {day_offset} of your subscription.</p>
        <p>Let’s get started with your Finance Agent tools today.</p>
        """

    return send_email(email, subject, html)
