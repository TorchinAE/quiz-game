"""Telegram bot for quiz game notifications and admin commands."""

import logging

from app.config import TELEGRAM_ADMIN_ID, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

_bot = None
_bot_app = None


async def start_bot():
    """Start the telegram bot as a background task."""
    global _bot, _bot_app
    if not TELEGRAM_BOT_TOKEN:
        logger.info("Telegram bot disabled (no token)")
        return

    try:
        from telegram import Bot
        from telegram.ext import Application, CommandHandler

        _bot = Bot(token=TELEGRAM_BOT_TOKEN)

        _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        _bot_app.add_handler(CommandHandler("start", cmd_start))
        _bot_app.add_handler(CommandHandler("stats", cmd_stats))
        _bot_app.add_handler(CommandHandler("top", cmd_top))
        _bot_app.add_handler(CommandHandler("votes", cmd_votes))
        _bot_app.add_handler(CommandHandler("backup", cmd_backup))

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


def _is_admin(update) -> bool:
    if not TELEGRAM_ADMIN_ID:
        return False
    return str(update.effective_user.id) == str(TELEGRAM_ADMIN_ID)


async def cmd_start(update, context):
    if not _is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        "Квиз-Бот Администратора\n\n"
        "Доступные команды:\n"
        "/stats — статистика\n"
        "/top — топ игроков\n"
        "/votes — предложенные темы\n"
        "/backup — создать бэкап"
    )


async def cmd_stats(update, context):
    if not _is_admin(update):
        return
    try:
        from sqlalchemy import func, select

        from app.database import async_session
        from app.models import Room, VisitStats

        async with async_session() as db:
            visit_count = (await db.execute(select(func.count(VisitStats.id)))).scalar() or 0
            active_rooms = (
                await db.execute(select(func.count(Room.id)).where(Room.status.in_(["waiting", "active"])))
            ).scalar() or 0
            total_rooms = (await db.execute(select(func.count(Room.id)))).scalar() or 0

        text = (
            f"Статистика\n\n"
            f"Всего посещений: {visit_count}\n"
            f"Активных комнат: {active_rooms}\n"
            f"Всего комнат: {total_rooms}"
        )
        await update.message.reply_text(text)
    except Exception:
        await update.message.reply_text("Ошибка получения статистики")


async def cmd_top(update, context):
    if not _is_admin(update):
        return
    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models import Player

        async with async_session() as db:
            result = await db.execute(select(Player).order_by(Player.total_score.desc()).limit(10))
            players = result.scalars().all()

        if not players:
            await update.message.reply_text("Нет игроков")
            return

        lines = ["Топ-10 игроков\n"]
        for i, p in enumerate(players, 1):
            lines.append(f"{i}. {p.nickname}: {p.total_score} очков ({p.games_played} игр)")
        await update.message.reply_text("\n".join(lines))
    except Exception:
        await update.message.reply_text("Ошибка получения топа")


async def cmd_votes(update, context):
    if not _is_admin(update):
        return
    try:
        from sqlalchemy import func, select

        from app.database import async_session
        from app.models import SuggestedTopic, TopicVote

        async with async_session() as db:
            result = await db.execute(
                select(
                    SuggestedTopic.name,
                    SuggestedTopic.suggested_by,
                    func.coalesce(func.sum(TopicVote.vote), 0).label("rating"),
                )
                .outerjoin(TopicVote)
                .group_by(SuggestedTopic.id)
                .order_by(func.coalesce(func.sum(TopicVote.vote), 0).desc())
                .limit(10)
            )
            rows = result.all()

        if not rows:
            await update.message.reply_text("Нет предложенных тем")
            return

        lines = ["Предложенные темы\n"]
        for name, author, rating in rows:
            sign = "+" if rating > 0 else ""
            lines.append(f"{sign}{rating} — {name} (от {author})")
        await update.message.reply_text("\n".join(lines))
    except Exception:
        await update.message.reply_text("Ошибка получения голосований")


async def cmd_backup(update, context):
    if not _is_admin(update):
        return
    try:
        await update.message.reply_text("Создаю бэкап...")
        from app.backup import create_backup, upload_backup

        path = await create_backup()
        uploaded = await upload_backup(path)
        status = "загружен на сервер" if uploaded else "сохранён локально"
        await update.message.reply_text(f"Бэкап {status}: {path}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка бэкапа: {e}")


async def notify_new_topic(topic_name: str):
    """Send notification when a new topic is created."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        await _bot.send_message(
            chat_id=TELEGRAM_ADMIN_ID,
            text=f"Новая тема создана: {topic_name}",
        )
    except Exception:
        pass


async def notify_backup_complete():
    """Send notification when backup completes."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        await _bot.send_message(
            chat_id=TELEGRAM_ADMIN_ID,
            text="Бэкап завершён успешно",
        )
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
            f"Еженедельный отчёт\n\n"
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
