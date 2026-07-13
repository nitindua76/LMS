"""
Minimal SMTP sender. No email-sending path existed anywhere in this repo
before session reminders needed one, despite Mailpit already being
provisioned in docker-compose.yml — this fills that gap. Swap for a queued
sender if volume ever outgrows a synchronous SMTP call from a background job.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(msg)
