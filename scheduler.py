from app.utils.mailer import send_email_html

def job_send_trial_email(user):
    context = {
        "first_name": user.get("first_name", "User"),
        "agent_id": user.get("agent_id", 1),
    }
    send_email_html(
        subject="Welcome to Your Trial",
        template_name="email_day1.html",
        context=context,
        receiver=user.get("email"),
    )
