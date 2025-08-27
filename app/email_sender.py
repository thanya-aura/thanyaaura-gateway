# app/email_sender.py
import os
import smtplib
import unicodedata
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from jinja2 import Environment, FileSystemLoader

# ---------------- Jinja env ----------------
env = Environment(loader=FileSystemLoader("app/templates"))

def clean_text(value: str) -> str:
    """
    Legacy 'clean' filter: normalize common punctuation and NBSP.
    """
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
NBSP = "\xa0"

def _sanitize(text: str | None) -> str:
    """
    Normalize to NFKC and replace NBSP with normal spaces to avoid hidden Unicode issues.
    """
    if text is None:
        return ""
    return unicodedata.normalize("NFKC", str(text)).replace(NBSP, " ")

def _ascii_credential(raw: str | None, name_for_log: str) -> str:
    """
    Ensure credentials/envelope addresses are ASCII (SMTP AUTH and envelope are ASCII on many servers).
    We keep message content UTF-8; only creds/envelopes are constrained.
    """
    s = _sanitize(raw).strip()
    try:
        s.encode("ascii")
        return s
    except UnicodeEncodeError:
        # Remove non-ASCII codepoints (e.g., NBSP, smart quotes)
        ascii_only = "".join(ch for ch in s if ord(ch) < 128)
        print(
            f"[email_warn] {name_for_log} contained non-ASCII characters and was sanitized. "
            "Retype this value in your environment (avoid copy/paste)."
        )
        return ascii_only

def _bool_env(name: str) -> bool:
    return (_sanitize(os.getenv(name)) or "").lower() in {"1", "true", "yes", "on"}

# ---------------- Email config ----------------
# Accept both SMTP_SERVER and SMTP_HOST (HOST is common in some dashboards)
SMTP_SERVER = _sanitize(os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST") or "smtp.gmail.com")
try:
    SMTP_PORT = int(_sanitize(os.getenv("SMTP_PORT") or "587"))
except ValueError:
    SMTP_PORT = 587

# ASCII-only creds for SMTP AUTH
SMTP_USER = _ascii_credential(os.getenv("SMTP_USER") or "", "SMTP_USER")
SMTP_PASS = _ascii_credential(os.getenv("SMTP_PASS") or "", "SMTP_PASS")

# Envelope From must be ASCII for many MTAs; use FROM_EMAIL if provided, else fallback to SMTP_USER
FROM_EMAIL = _ascii_credential(os.getenv("FROM_EMAIL") or SMTP_USER or "no-reply@thanyaaura.com", "FROM_EMAIL")
# Display name can be UTF-8
FROM_NAME = _sanitize(os.getenv("FROM_NAME") or "Thanyaaura")

DISABLE_EMAIL = _bool_env("DISABLE_EMAIL")

# ---------------- Core ----------------
def render_template(template_name: str, context: dict) -> str:
    tpl = env.get_template(template_name)
    html = tpl.render(**context)
    return _sanitize(html)

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    UTF-8 safe sender:
      - Subject & From display name encoded as UTF-8 headers
      - HTML body in UTF-8
      - SMTP credentials & envelope addresses sanitized to ASCII
    """
    subject_str = _sanitize(subject)
    html_str = _sanitize(html_content)
    to_ascii = _ascii_credential(to_email, "TO_EMAIL")

    # Build message (UTF-8 content)
    msg = MIMEText(html_str, "html", "utf-8")
    msg["Subject"] = str(Header(subject_str, "utf-8"))
    msg["From"] = formataddr((str(Header(FROM_NAME, "utf-8")), FROM_EMAIL))
    msg["To"] = to_ascii

    # Dry-run switch (useful locally)
    if DISABLE_EMAIL or not SMTP_USER or not SMTP_PASS:
        print(f"[email_stub] Would send to {to_ascii}: {subject_str}")
        return True

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            # TLS if supported
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPException:
                pass
            server.login(SMTP_USER, SMTP_PASS)  # Python encodes this as ASCII
            server.sendmail(FROM_EMAIL, [to_ascii], msg.as_string())
        return True
    except UnicodeEncodeError as e:
        print(
            f"[email_error] Non-ASCII in SMTP credentials/envelope caused login failure: {e}. "
            "Please retype SMTP_USER/SMTP_PASS/FROM_EMAIL in the dashboard (avoid copy/paste)."
        )
        return False
    except Exception as e:
        print(f"[email_error] SMTP send failed: {e}")
        return False

def send_trial_email(day: int, user: dict, agent_name: str, links: dict) -> bool:
    """
    Helper for the scheduler (Day 1 / 10 / 23).
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
