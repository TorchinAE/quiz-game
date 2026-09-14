"""Email notification helpers. No-op when SMTP is not configured."""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import ADMIN_MAIL, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_SSL, SMTP_USE_TLS, SMTP_USER

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(ADMIN_MAIL and SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


async def _send_email(subject: str, body: str):
    if not _smtp_configured():
        return

    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_MAIL
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=SMTP_USE_SSL,
            start_tls=SMTP_USE_TLS and not SMTP_USE_SSL,
        )
    except Exception:
        logger.exception("Failed to send email notification")


async def notify_suggestion_pending_email(topic_id: int, name: str, suggested_by: str):
    await _send_email(
        subject="Quiz: новая предложенная тема",
        body=f"Тема «{name}» от {suggested_by} (id={topic_id}) ожидает модерации.",
    )


async def notify_backup_complete_email():
    await _send_email(
        subject="Quiz: бэкап завершён",
        body="Автоматический бэкап успешно создан и загружен.",
    )


async def notify_new_topic_email(topic_name: str):
    await _send_email(
        subject="Quiz: новая тема",
        body=f"Создана новая тема: «{topic_name}».",
    )


async def send_weekly_report_email(report: str):
    await _send_email(
        subject="Quiz: еженедельный отчёт",
        body=report,
    )
