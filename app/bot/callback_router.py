"""Central callback query router and text input handler."""

import logging

from .utils import _is_admin, home_keyboard, safe_edit_message

logger = logging.getLogger(__name__)


async def handle_callback(update, context):
    """Single entry point for all callback queries."""
    if not _is_admin(update):
        await update.callback_query.answer("⛔ Нет доступа", show_alert=True)
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "noop":
        return

    section = data.split(":")[0]

    from .backup import handle_backup
    from .menus import show_main_menu
    from .moderation import handle_moderation
    from .players import handle_top_players
    from .questions import handle_questions
    from .stats import handle_stats
    from .suggestions import handle_suggestions
    from .topics import handle_topics

    handlers = {
        "mn": show_main_menu,
        "t": handle_topics,
        "q": handle_questions,
        "s": handle_stats,
        "v": handle_suggestions,
        "p": handle_moderation,
        "tp": handle_top_players,
        "bk": handle_backup,
    }

    handler = handlers.get(section)
    if handler:
        try:
            await handler(update, context, data)
        except Exception:
            logger.exception(f"Handler error for {data}")
            await safe_edit_message(query, "⚠️ Произошла ошибка", reply_markup=home_keyboard())
    else:
        logger.warning(f"Unknown callback: {data}")


async def handle_text_input(update, context):
    """Route free-text messages to the active multi-step flow."""
    if not _is_admin(update):
        return
    flow = context.user_data.get("flow")
    if not flow:
        return
    from .flows import dispatch_flow_step

    await dispatch_flow_step(update, context, flow)


async def handle_photo_input(update, context):
    """Handle photo messages for image upload flow."""
    if not _is_admin(update):
        return
    flow = context.user_data.get("flow")
    if not flow or flow.get("type") != "question_image_upload":
        return

    import os
    import uuid

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.bot.questions import PICTURES_DIR
    from app.bot.utils import home_keyboard

    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        os.makedirs(PICTURES_DIR, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(PICTURES_DIR, filename)
        await file.download_to_drive(filepath)

        question_id = flow["data"]["question_id"]
        url = f"/pictures/{filename}"

        from sqlalchemy import select

        from app.database import async_session
        from app.models import Question

        async with async_session() as db:
            result = await db.execute(select(Question).where(Question.id == question_id))
            q = result.scalar_one_or_none()
            if q:
                q.image_url = url
                await db.commit()

        del context.user_data["flow"]

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("◀️ К вопросу", callback_data=f"q:vw:{question_id}"),
                    InlineKeyboardButton("🏠 Меню", callback_data="mn"),
                ]
            ]
        )
        await update.message.reply_text(f"✅ Фото загружено и установлено:\n{url}", reply_markup=kb)
    except Exception:
        logger.exception("Photo upload failed")
        await update.message.reply_text("❌ Ошибка загрузки фото", reply_markup=home_keyboard())
