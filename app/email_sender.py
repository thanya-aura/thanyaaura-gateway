import os
import smtplib
import unicodedata
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader

# ---------------- Email setup ----------------
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "no-reply@thanyaaura.com")

# ---------------- Jinja2 setup ----------------
env = Environment(loader=FileSystemLoader("app/templates"))

# ---------------- Sanitizer ----------------
def clean_text(value: str) -> str:
    """Remove problematic unicode (non-breaking spaces, curly quotes, dashes)."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)  # normalize all characters
    return (
        value.replace("\xa0", " ")   # non-breaking space
             .replace("–", "-")
             .replace("—", "-")
             .replace("“", '"')
             .replace("”", '"')
             .replace("’", "'")
             .replace("‘", "'")
    )

# Add filter for Jinja templates
env.filters["clean"] = clean_text

# ---------------- Helpers ----------------
def render_template(template_name: str, context: dict) -> str:
    """Render + sanitize HTML template."""
    template = env.get_template(template_name)
    html = template.render(**context)
    return clean_text(html)

def send_email(to_email: str, subject: str, html_content: str):
    """Send sanitized HTML email using UTF-8."""
    msg = MIMEText(clean_text(html_content), "html", "utf-8")  # ensure utf-8 safe
    msg["Subject"] = clean_text(subject)
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [to_email], msg.as_string())
            print(f"✅ Email sent to {to_email}: {subject}")
    except Exception as ex:
        print(f"❌ Email error to {to_email}: {ex}")

# ---------------- Trial Email Logic ----------------
def send_trial_email(day: int, user, agent_name: str, links: dict):
    """
    Send trial emails on day 1, 10, 23.
    Skip if user is the permanent admin account.
    """
    if user["user_email"].lower() == "thanyaaura@email.com":
        print(f"⚠️ Skipping trial email for permanent admin {user['user_email']}")
        return

    template_map = {
        1: ("email_day1.html", "Welcome to your Finance AI Agent - Day 1"),
        10: ("email_day10.html", "Case Study & Tips - Day 10"),
        23: ("email_day23.html", "Executive Insights - Day 23"),
    }

    if day not in template_map:
        print(f"⚠️ No template for Day {day}")
        return

    template_file, subject = template_map[day]

    context = {
        "first_name": user.get("first_name", "there"),
        "agent_name": agent_name,
        "platform": user.get("platform", "GPT"),
        "gpt_link": links.get("gpt_link"),
        "gemini_link": links.get("gemini_link"),
        "copilot_link": links.get("copilot_link"),
        "upgrade_link": links.get("upgrade_link"),
    }

    html_content = render_template(template_file, context)
    send_email(user["user_email"], subject, html_content)
