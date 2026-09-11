from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _mock_update(user_id=12345, text="/start"):
    """Create a mock telegram Update object."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    return update


async def test_is_admin_with_matching_id():
    with patch("app.bot.utils.TELEGRAM_ADMIN_ID", "12345"):
        from app.telegram_bot import _is_admin

        update = _mock_update(user_id=12345)
        assert _is_admin(update) is True


async def test_is_admin_with_wrong_id():
    with patch("app.bot.utils.TELEGRAM_ADMIN_ID", "99999"):
        from app.telegram_bot import _is_admin

        update = _mock_update(user_id=12345)
        assert _is_admin(update) is False


async def test_is_admin_with_empty_admin_id():
    with patch("app.bot.utils.TELEGRAM_ADMIN_ID", ""):
        from app.telegram_bot import _is_admin

        update = _mock_update(user_id=12345)
        assert _is_admin(update) is False


async def test_cmd_start_as_admin():
    with patch("app.bot.utils.TELEGRAM_ADMIN_ID", "12345"):
        from app.bot.menus import cmd_start

        update = _mock_update(user_id=12345)
        context = MagicMock()
        await cmd_start(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "администратора" in text.lower()


async def test_cmd_start_as_non_admin():
    with patch("app.bot.utils.TELEGRAM_ADMIN_ID", "99999"):
        from app.bot.menus import cmd_start

        update = _mock_update(user_id=12345)
        context = MagicMock()
        await cmd_start(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "нет доступа" in text.lower()


async def test_notify_new_topic_no_bot():
    """Should not raise when bot is not initialized."""
    with patch("app.telegram_bot._bot", None):
        from app.telegram_bot import notify_new_topic

        await notify_new_topic("Test Topic")


async def test_notify_backup_complete_no_bot():
    """Should not raise when bot is not initialized."""
    with patch("app.telegram_bot._bot", None):
        from app.telegram_bot import notify_backup_complete

        await notify_backup_complete()


async def test_send_weekly_report_no_bot():
    """Should not raise when bot is not initialized."""
    with patch("app.telegram_bot._bot", None):
        from app.telegram_bot import send_weekly_report

        await send_weekly_report()


async def test_start_bot_no_token():
    """Bot should not start when token is empty."""
    with patch("app.telegram_bot.TELEGRAM_BOT_TOKEN", ""):
        from app.telegram_bot import start_bot

        await start_bot()
        # Should remain None (no crash)
        from app import telegram_bot

        assert telegram_bot._bot_app is None


async def test_stop_bot_when_not_started():
    """stop_bot should not raise when nothing was started."""
    from app.telegram_bot import stop_bot

    await stop_bot()
