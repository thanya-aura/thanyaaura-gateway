import os
import smtplib
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def render_template(template_name, **kwargs):
    template = env.get_template(template_name)
    return template.render(**kwargs)

def send_email(subject, template_name, **kwargs):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receiver = kwargs.get("email_to", os.getenv("EMAIL_TO"))

    body = render_template(template_name, **kwargs)

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, receiver.split(","), msg.as_string())
