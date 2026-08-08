import os
import logging
import resend

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, code: str) -> None:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise ValueError("RESEND_API_KEY is not configured in the environment.")

    resend.api_key = api_key
    sender = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    subject = "Your HireHub account verification code"
    html_content = (
        f"Your HireHub account verification code is: <strong>{code}</strong><br><br>"
        "It expires in 10 minutes. If you did not request this, you can ignore this email."
    )

    params: resend.Emails.SendParams = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }

    logger.info("Attempting to send Resend email to %s (from=%s)", to_email, sender)
    res = resend.Emails.send(params)
    logger.info("Resend email sent successfully. ID: %s", getattr(res, "id", None))
