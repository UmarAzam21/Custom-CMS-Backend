import smtplib
from email.message import EmailMessage

from app.support_system.config import settings


def send_email(
    to_address: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    from_address: str | None = None,
) -> None:
    """Send a plain-text email via SMTP.

    reply_to: if set, replies from the customer's mail client will go to this
    address instead of `from_address` — this is how ticket+<id>@yourdomain.com
    routing works.
    """
    msg = EmailMessage()
    from_addr = from_address or settings.SMTP_USER
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{from_addr}>"
    msg["To"] = to_address
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
