"""Telegram bot for quiz game notifications and admin commands."""

import logging

from app.config import TELEGRAM_ADMIN_ID, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

_bot = None
_bot_app = None

# Track admin edit flow: {admin_chat_id: {"topic_id": int, "message_id": int}}
_pending_edits: dict[int, dict] = {}


async def start_bot():
    """Start the telegram bot as a background task."""
    global _bot, _bot_app
    if not TELEGRAM_BOT_TOKEN:
        logger.info("Telegram bot disabled (no token)")
        return

    try:
        from telegram import Bot
        from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

        _bot = Bot(token=TELEGRAM_BOT_TOKEN)

        _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        _bot_app.add_handler(CommandHandler("start", cmd_start))
        _bot_app.add_handler(CommandHandler("stats", cmd_stats))
        _bot_app.add_handler(CommandHandler("top", cmd_top))
        _bot_app.add_handler(CommandHandler("votes", cmd_votes))
        _bot_app.add_handler(CommandHandler("pending", cmd_pending))
        _bot_app.add_handler(CommandHandler("backup", cmd_backup))
        _bot_app.add_handler(CallbackQueryHandler(handle_suggestion_callback, pattern=r"^suggest_"))
        _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_text))

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


# --- Commands ---


async def cmd_start(update, context):
    if not _is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        "Квиз-Бот Администратора\n\n"
        "Доступные команды:\n"
        "/stats — статистика\n"
        "/top — топ игроков\n"
        "/votes — темы на голосовании\n"
        "/pending — темы на модерации\n"
        "/backup — создать бэкап\n\n"
        "Предложенные темы приходят сюда автоматически.\n"
        "Используйте кнопки для одобрения/правки/отклонения."
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
                .where(SuggestedTopic.status == "approved")
                .group_by(SuggestedTopic.id)
                .order_by(func.coalesce(func.sum(TopicVote.vote), 0).desc())
                .limit(10)
            )
            rows = result.all()

        if not rows:
            await update.message.reply_text("Нет тем на голосовании")
            return

        lines = ["Темы на голосовании\n"]
        for name, author, rating in rows:
            sign = "+" if rating > 0 else ""
            lines.append(f"{sign}{rating} — {name} (от {author})")
        await update.message.reply_text("\n".join(lines))
    except Exception:
        await update.message.reply_text("Ошибка получения голосований")


async def cmd_pending(update, context):
    if not _is_admin(update):
        return
    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models import SuggestedTopic

        async with async_session() as db:
            result = await db.execute(
                select(SuggestedTopic)
                .where(SuggestedTopic.status == "pending")
                .order_by(SuggestedTopic.created_at.desc())
            )
            topics = result.scalars().all()

        if not topics:
            await update.message.reply_text("Нет тем на модерации")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        for t in topics:
            text = f"📝 «{t.name}»\nот {t.suggested_by}"
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Одобрить", callback_data=f"suggest_approve_{t.id}"),
                        InlineKeyboardButton("✏️ Править", callback_data=f"suggest_edit_{t.id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"suggest_reject_{t.id}"),
                    ]
                ]
            )
            await update.message.reply_text(text, reply_markup=keyboard)
    except Exception:
        await update.message.reply_text("Ошибка получения тем")


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


# --- Suggestion notification & inline buttons ---


async def notify_suggestion_pending(topic_id: int, name: str, suggested_by: str):
    """Send new suggestion to admin with approve/edit/reject buttons."""
    if not _bot or not TELEGRAM_ADMIN_ID:
        return
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        text = f"💡 Новая предложенная тема:\n\n«{name}»\nот {suggested_by}"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"suggest_approve_{topic_id}"),
                    InlineKeyboardButton("✏️ Править", callback_data=f"suggest_edit_{topic_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"suggest_reject_{topic_id}"),
                ]
            ]
        )
        await _bot.send_message(
            chat_id=TELEGRAM_ADMIN_ID,
            text=text,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Failed to notify admin about suggestion")


async def handle_suggestion_callback(update, context):
    """Handle inline button presses for suggestion moderation."""
    if not _is_admin(update):
        return

    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. "suggest_approve_5", "suggest_edit_5", "suggest_reject_5"
    parts = data.split("_", 2)
    if len(parts) != 3:
        return

    action = parts[1]  # approve / edit / reject
    try:
        topic_id = int(parts[2])
    except ValueError:
        return

    if action == "approve":
        await _do_approve(query, topic_id)
    elif action == "reject":
        await _do_reject(query, topic_id)
    elif action == "edit":
        await _do_edit_start(query, topic_id)


async def _do_approve(query, topic_id: int):
    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models import SuggestedTopic

        async with async_session() as db:
            result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
            topic = result.scalar_one_or_none()
            if not topic:
                await query.edit_message_text("Тема не найдена")
                return

            topic.status = "approved"
            name = topic.name
            await db.commit()

        await query.edit_message_text(f"✅ Одобрено: «{name}»\nТеперь доступно для голосования.")
    except Exception:
        await query.edit_message_text("Ошибка при одобрении")


async def _do_reject(query, topic_id: int):
    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models import SuggestedTopic

        async with async_session() as db:
            result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
            topic = result.scalar_one_or_none()
            if not topic:
                await query.edit_message_text("Тема не найдена")
                return

            name = topic.name
            topic.status = "rejected"
            await db.commit()

        await query.edit_message_text(f"❌ Отклонено: «{name}»")
    except Exception:
        await query.edit_message_text("Ошибка при отклонении")


async def _do_edit_start(query, topic_id: int):
    """Start edit flow — ask admin for new text."""
    chat_id = query.message.chat_id

    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models import SuggestedTopic

        async with async_session() as db:
            result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
            topic = result.scalar_one_or_none()
            if not topic:
                await query.edit_message_text("Тема не найдена")
                return
            current_name = topic.name
    except Exception:
        await query.edit_message_text("Ошибка")
        return

    _pending_edits[chat_id] = {"topic_id": topic_id, "message_id": query.message.message_id}

    await query.edit_message_text(
        f"✏️ Текущая формулировка:\n«{current_name}»\n\nОтправьте новый текст темы (или /cancel для отмены):"
    )


async def handle_edit_text(update, context):
    """Handle text messages — check if admin is in edit flow."""
    chat_id = update.message.chat_id
    if chat_id not in _pending_edits:
        return

    if not _is_admin(update):
        return

    text = update.message.text.strip()
    if not text or len(text) > 120:
        await update.message.reply_text("Текст должен быть от 1 до 120 символов. Попробуйте ещё раз:")
        return

    pending = _pending_edits.pop(chat_id)
    topic_id = pending["topic_id"]

    try:
        from sqlalchemy import select
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from app.database import async_session
        from app.models import SuggestedTopic

        async with async_session() as db:
            result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
            topic = result.scalar_one_or_none()
            if not topic:
                await update.message.reply_text("Тема не найдена")
                return

            old_name = topic.name
            topic.name = text
            await db.commit()

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"suggest_approve_{topic_id}"),
                    InlineKeyboardButton("✏️ Править", callback_data=f"suggest_edit_{topic_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"suggest_reject_{topic_id}"),
                ]
            ]
        )
        await update.message.reply_text(
            f"✏️ Формулировка обновлена:\n\nБыло: «{old_name}»\nСтало: «{text}»\n\nЧто сделать с темой?",
            reply_markup=keyboard,
        )
    except Exception:
        await update.message.reply_text("Ошибка при обновлении темы")


# --- Notification functions ---


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
