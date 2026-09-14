"""Tests for email notification module."""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_send_email_noop_when_not_configured():
    """Email sending is a no-op when SMTP is not configured."""
    with patch("app.email_notifier._smtp_configured", return_value=False):
        from app.email_notifier import _send_email

        await _send_email("subject", "body")  # should not raise


@patch("app.email_notifier._smtp_configured", return_value=True)
@patch("app.email_notifier.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_email_sends(mock_send, _mock_cfg):
    from app.email_notifier import _send_email

    await _send_email("Test Subject", "Test body")
    mock_send.assert_called_once()


@patch("app.email_notifier._smtp_configured", return_value=True)
@patch("app.email_notifier.aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("smtp down"))
async def test_send_email_handles_error(mock_send, _mock_cfg):
    from app.email_notifier import _send_email

    await _send_email("Test Subject", "Test body")  # should not raise


@patch("app.email_notifier._send_email", new_callable=AsyncMock)
async def test_notify_suggestion_pending_email(mock_send):
    from app.email_notifier import notify_suggestion_pending_email

    await notify_suggestion_pending_email(42, "Test Topic", "Alice")
    mock_send.assert_called_once()
    args = mock_send.call_args
    assert "Test Topic" in args.kwargs.get("body", args[1].get("body", "") if len(args) > 1 else "")
    assert "Alice" in args.kwargs.get("body", args[1].get("body", "") if len(args) > 1 else "")


@patch("app.email_notifier._send_email", new_callable=AsyncMock)
async def test_notify_backup_complete_email(mock_send):
    from app.email_notifier import notify_backup_complete_email

    await notify_backup_complete_email()
    mock_send.assert_called_once()


@patch("app.email_notifier._send_email", new_callable=AsyncMock)
async def test_send_weekly_report_email(mock_send):
    from app.email_notifier import send_weekly_report_email

    report = "Visits: 100\nGames: 50"
    await send_weekly_report_email(report)
    mock_send.assert_called_once()
    args = mock_send.call_args
    assert "Visits: 100" in args.kwargs.get("body", args[1].get("body", "") if len(args) > 1 else "")
