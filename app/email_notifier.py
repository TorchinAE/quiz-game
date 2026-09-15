"""Email notification helpers. No-op when SMTP is not configured."""

import asyncio
import logging
from datetime import datetime
from email.message import EmailMessage

import aiosmtplib

from app.config import ADMIN_MAIL, BASE_URL, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_SSL, SMTP_USE_TLS, SMTP_USER

logger = logging.getLogger(__name__)


def send_email_in_background(subject: str, body: str, html: str | None = None):
    """Fire-and-forget email send in a background task."""
    asyncio.create_task(_send_email(subject=subject, body=body, html=html))


def _smtp_configured() -> bool:
    return bool(ADMIN_MAIL and SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def _base_url() -> str:
    """Return BASE_URL without trailing slash (e.g. http://host/quiz)."""
    return BASE_URL.rstrip("/")


def _admin_url() -> str:
    """Link to the admin panel page."""
    return f"{_base_url()}/к2к1"


async def _send_email(subject: str, body: str, html: str | None = None):
    if not _smtp_configured():
        return

    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_MAIL
    msg["Subject"] = subject
    if html:
        msg.set_content(body)
        msg.add_alternative(html, subtype="html")
    else:
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


async def notify_suggestion_pending_email(
    topic_id: int,
    name: str,
    suggested_by: str,
    created_at: datetime | None = None,
    votes_up: int = 0,
    votes_down: int = 0,
):
    admin = _admin_url()
    api_base = _base_url()
    approve_url = f"{api_base}/api/suggestions/{topic_id}/approve"
    reject_url = f"{api_base}/api/suggestions/{topic_id}/reject"
    time_str = created_at.strftime("%d.%m.%Y %H:%M UTC") if created_at else "неизвестно"

    plain = (
        f"Тема «{name}» от {suggested_by} ({time_str}) ожидает модерации.\n"
        f"Голоса: +{votes_up} / -{votes_down}\n\n"
        f"Одобрить: {approve_url}\n"
        f"Отклонить: {reject_url}\n"
        f"Панель: {admin}\n"
    )

    html = f"""\
<html>
<body style="font-family:Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:24px;">
  <div style="max-width:520px;margin:0 auto;background:#16213e;border-radius:12px;padding:28px;">
    <h2 style="color:#e94560;margin-top:0;">Quiz — новая тема на модерацию</h2>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr>
        <td style="padding:6px 0;color:#888;">Тема</td>
        <td style="padding:6px 0;font-weight:bold;color:#fff;">«{name}»</td>
      </tr>
      <tr><td style="padding:6px 0;color:#888;">От</td><td style="padding:6px 0;color:#fff;">{suggested_by}</td></tr>
      <tr><td style="padding:6px 0;color:#888;">Когда</td><td style="padding:6px 0;color:#fff;">{time_str}</td></tr>
      <tr><td style="padding:6px 0;color:#888;">ID</td><td style="padding:6px 0;color:#fff;">{topic_id}</td></tr>
    </table>

    <div style="background:#0f3460;border-radius:8px;padding:14px;margin:16px 0;text-align:center;">
      <span style="color:#53d769;font-size:20px;font-weight:bold;">+{votes_up}</span>
      <span style="color:#888;margin:0 12px;">/</span>
      <span style="color:#e94560;font-size:20px;font-weight:bold;">-{votes_down}</span>
      <div style="color:#888;font-size:12px;margin-top:4px;">голосов</div>
    </div>

    <div style="text-align:center;margin:24px 0;">
      <a href="{approve_url}"
         style="display:inline-block;background:#53d769;color:#000;text-decoration:none;
                font-weight:bold;padding:14px 32px;border-radius:8px;margin:0 8px;font-size:15px;">
        &#10003; Одобрить
      </a>
      <a href="{reject_url}"
         style="display:inline-block;background:#e94560;color:#fff;text-decoration:none;
                font-weight:bold;padding:14px 32px;border-radius:8px;margin:0 8px;font-size:15px;">
        &#10007; Отклонить
      </a>
    </div>

    <p style="text-align:center;margin-top:20px;">
      <a href="{admin}" style="color:#0f9dce;text-decoration:none;">Открыть панель администратора</a>
    </p>
  </div>
</body>
</html>"""

    await _send_email(
        subject=f"Quiz: новая тема «{name}» — модерация",
        body=plain,
        html=html,
    )


def notify_suggestion_pending_email_in_background(
    topic_id: int,
    name: str,
    suggested_by: str,
    created_at: datetime | None = None,
    votes_up: int = 0,
    votes_down: int = 0,
):
    """Fire-and-forget version of notify_suggestion_pending_email."""
    asyncio.create_task(notify_suggestion_pending_email(topic_id, name, suggested_by, created_at, votes_up, votes_down))


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
