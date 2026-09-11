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
