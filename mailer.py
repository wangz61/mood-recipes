"""Outgoing email: SMTP when configured, otherwise printed to the console (or kept in memory for tests)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from fastapi.concurrency import run_in_threadpool

from config import Settings

log = logging.getLogger("mood_recipes.mail")


def _send_smtp(settings: Settings, msg: EmailMessage) -> None:
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=20) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=context)
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


async def send_email(settings: Settings, outbox: list[EmailMessage], to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user or "Mood Recipes <no-reply@localhost>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if settings.mail_backend == "memory":
        outbox.append(msg)
    elif settings.mail_backend == "smtp":
        try:
            await run_in_threadpool(_send_smtp, settings, msg)
        except (OSError, smtplib.SMTPException):
            # Don't tell the requester; the response must look the same either way.
            log.exception("Could not send email to %s", to)
    else:
        print(f"\n--- Email (no SMTP configured) ---\nTo: {to}\nSubject: {subject}\n\n{body}\n---------------------------------\n", flush=True)
