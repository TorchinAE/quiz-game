"""Telegram bot entry point. Thin wrapper over app/bot/ package."""

import logging

from app.config import TELEGRAM_ADMIN_ID, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

_bot = None
_bot_app = None

# Re-export for backward compatibility (used in tests)
from app.bot.utils import _is_admin  # noqa: E402, F401


async def start_bot():
    """Start the telegram bot as a background task."""
    global _bot, _bot_app
    if not TELEGRAM_BOT_TOKEN:
        logger.info("Telegram bot disabled (no token)")
        return

    try:
        from telegram import Bot
        from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

        from app.bot.callback_router import handle_callback, handle_text_input
        from app.bot.menus import cmd_start

        _bot = Bot(token=TELEGRAM_BOT_TOKEN)

        _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        _bot_app.add_handler(CommandHandler("start", cmd_start))
        _bot_app.add_handler(CallbackQueryHandler(handle_callback))
        _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

        await _bot_app.initialize()
        await _bot_app.start()
        await _bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")
    except Exception:
        logger.exception("Failed to start telegram bot")


async def stop_bot():
    """Stop the telegram bot."""
    global _bot, _bot_app
    if _bot_app:
        try:
            await _bot_app.updater.stop()
            await _bot_app.stop()
            await _bot_app.shutdown()
        except Exception:
            pass
    _bot = None
    _bot_app = None


# --- Notification functions (called externally) ---


async def notify_suggestion_pending(topic_id: int, name: str, suggested_by: str):
    """Send new suggestion to admin with approve/reject buttons."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        text = f"💡 Новая предложенная тема:\n\n«{name}»\nот {suggested_by}"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"p:ap:{topic_id}"),
                    InlineKeyboardButton("✏️ Править", callback_data=f"p:ed:{topic_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"p:rj:{topic_id}"),
                ]
            ]
        )
        await _bot.send_message(chat_id=TELEGRAM_ADMIN_ID, text=text, reply_markup=keyboard)
    except Exception:
        logger.exception("Failed to notify admin about suggestion")


async def notify_new_topic(topic_name: str):
    """Send notification when a new topic is created."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="mn")]])
        await _bot.send_message(chat_id=TELEGRAM_ADMIN_ID, text=f"🆕 Новая тема: {topic_name}", reply_markup=kb)
    except Exception:
        pass


async def notify_backup_complete():
    """Send notification when backup completes."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        await _bot.send_message(chat_id=TELEGRAM_ADMIN_ID, text="✅ Бэкап завершён успешно")
    except Exception:
        pass


async def send_weekly_report():
    """Generate and send weekly statistics report to admin."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func, select

        from app.database import async_session
        from app.models import Player, Room, VisitStats

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        async with async_session() as db:
            visit_count = (
                await db.execute(select(func.count(VisitStats.id)).where(VisitStats.visited_at >= week_ago))
            ).scalar() or 0

            games_started = (
                await db.execute(select(func.count(Room.id)).where(Room.started_at >= week_ago))
            ).scalar() or 0

            games_finished = (
                await db.execute(
                    select(func.count(Room.id)).where(
                        Room.status == "finished",
                        Room.started_at >= week_ago,
                    )
                )
            ).scalar() or 0

            top_result = await db.execute(select(Player).order_by(Player.total_score.desc()).limit(3))
            top_players = top_result.scalars().all()

        report = (
            f"📊 Еженедельный отчёт\n\n"
            f"Посещений: {visit_count}\n"
            f"Игр начато: {games_started}\n"
            f"Игр завершено: {games_finished}\n"
        )
        if top_players:
            report += "\nТоп-3 игрока:\n"
            for i, p in enumerate(top_players, 1):
                report += f"{i}. {p.nickname}: {p.total_score} очков\n"

        await _bot.send_message(chat_id=TELEGRAM_ADMIN_ID, text=report)
    except Exception:
        pass
