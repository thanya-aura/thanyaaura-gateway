# app/email_sender.py
import os
import smtplib
import unicodedata
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from jinja2 import Environment, FileSystemLoader

# ---------------- Email config ----------------
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "no-reply@thanyaaura.com")
FROM_NAME = os.environ.get("FROM_NAME", "Thanyaaura")

# ---------------- Jinja env ----------------
env = Environment(loader=FileSystemLoader("app/templates"))

# Keep your original “clean” filter logic (adds NBSP & punctuation fixes)
def clean_text(value: str) -> str:
    if not value:
        return ""
    return (
        value.replace("\xa0", " ")
             .replace("–", "-")
             .replace("—", "-")
             .replace("“", '"')
             .replace("”", '"')
             .replace("’", "'")
    )

env.filters["clean"] = clean_text

# ---------------- Helpers ----------------
def _sanitize(text: str) -> str:
    """
    Normalize to NFKC and replace NBSP with normal spaces to avoid ASCII header errors.
    """
    if text is None:
        return ""
    return unicodedata.normalize("NFKC", str(text)).replace("\xa0", " ")

def render_template(template_name: str, context: dict) -> str:
    tpl = env.get_template(template_name)
    # Let templates use the filter, but also sanitize final HTML to strip lurking NBSPs
    html = tpl.render(**context)
    return _sanitize(html)

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    UTF-8 safe email sender:
    - Subject encoded via Header('utf-8')
    - From header uses formataddr with UTF-8 display name
    - Body is UTF-8 HTML
    """
    subject = _sanitize(subject)
    from_name = _sanitize(FROM_NAME)

    # Build message (UTF-8 body)
    msg = MIMEText(_sanitize(html_content), "html", "utf-8")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = formataddr((str(Header(from_name, "utf-8")), FROM_EMAIL))
    msg["To"] = to_email

    # If SMTP creds are not set, no-op (keeps worker green in staging)
    if not SMTP_USER or not SMTP_PASS:
        print(f"[email_stub] Would send to {to_email}: {subject}")
        return True

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [to_email], msg.as_string())
    return True

def send_trial_email(day: int, user: dict, agent_name: str, links: dict) -> bool:
    """
    Helper for your scheduler (Day 1 / 10 / 23).
    Only uses UTF-8 safe send_email() above.
    """
    template_map = {
        1: "email_day1.html",
        10: "email_day10.html",
        23: "email_day23.html",
    }
    template_file = template_map.get(day)
    if not template_file:
        return False

    subject_map = {
        1: f"Welcome to {agent_name}!",
        10: f"Day 10: Tips to get more from {agent_name}",
        23: f"Day 23: You're close—unlock full power of {agent_name}",
    }
    subject = subject_map[day]

    context = {
        "first_name": user.get("first_name", "there"),
        "agent_name": agent_name,
        "platform": user.get("platform", "GPT"),
        "gpt_link": links.get("gpt_link"),
        "gemini_link": links.get("gemini_link"),
        "copilot_link": links.get("copilot_link"),
        "upgrade_link": links.get("upgrade_link"),
    }

    html = render_template(template_file, context)
    return send_email(user["user_email"], subject, html)
