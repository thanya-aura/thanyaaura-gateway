import os
import smtplib
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
import unicodedata

# Email setup
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "no-reply@thanyaaura.com")

# Jinja2 env for templates
env = Environment(loader=FileSystemLoader("app/templates"))

# -------- Helpers --------
def normalize_html(text: str) -> str:
    """
    Clean problematic unicode characters (non-breaking space, curly quotes, dashes).
    """
    if not text:
        return text
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Replace non-breaking spaces
    text = text.replace("\xa0", " ")
    # Replace fancy quotes/dashes with safe ASCII
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return text

def render_template(template_name: str, context: dict) -> str:
    template = env.get_template(template_name)
    raw_html = template.render(**context)
    return normalize_html(raw_html)

def send_email(to_email: str, subject: str, html_content: str):
    msg = MIMEText(html_content, "html", "utf-8")   # force UTF-8 safe
    msg["Subject"] = subject
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
