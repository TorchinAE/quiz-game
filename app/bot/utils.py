"""Shared utilities: admin check, keyboards, pagination, message editing."""

import logging

from app.config import TELEGRAM_ADMIN_ID

from .constants import PAGE_SIZE

logger = logging.getLogger(__name__)


def _is_admin(update) -> bool:
    if not TELEGRAM_ADMIN_ID:
        return False
    return str(update.effective_user.id) == str(TELEGRAM_ADMIN_ID)


def menu_keyboard(parent: str = ""):
    """Keyboard with [◀️ Назад | 🏠 Меню] row."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    row = []
    if parent:
        row.append(InlineKeyboardButton("◀️ Назад", callback_data=parent))
    row.append(InlineKeyboardButton("🏠 Меню", callback_data="mn"))
    return InlineKeyboardMarkup([row])


def cancel_keyboard(return_to: str = "mn"):
    """Keyboard with [❌ Отмена | 🏠 Меню] row."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("❌ Отмена", callback_data=return_to),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )


def home_keyboard():
    """Keyboard with just [🏠 Меню]."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="mn")]])


def build_paginated_keyboard(
    items: list,
    page: int,
    item_formatter,
    base_callback: str,
    parent_callback: str,
    extra_rows: list | None = None,
):
    """Build paginated inline keyboard. Returns (page, InlineKeyboardMarkup)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    total = len(items)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    page_items = items[start : start + PAGE_SIZE]

    rows = []
    if extra_rows:
        rows.extend(extra_rows)

    for item in page_items:
        text, cb = item_formatter(item)
        rows.append([InlineKeyboardButton(text, callback_data=cb)])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"{base_callback}:p{page - 1}"))
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"{base_callback}:p{page + 1}"))
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("◀️ Назад", callback_data=parent_callback),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ]
    )

    return page, InlineKeyboardMarkup(rows)


async def safe_edit_message(query, text: str, reply_markup=None):
    """Edit message text, handling 'message not modified' error silently."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.debug(f"Edit message failed: {e}")


async def edit_or_reply(update, context, text: str, reply_markup=None):
    """Edit the callback message if possible, otherwise send new."""
    query = getattr(update, "callback_query", None)
    if query:
        await safe_edit_message(query, text, reply_markup=reply_markup)
    else:
        msg = getattr(update, "message", None)
        if msg:
            await msg.reply_text(text, reply_markup=reply_markup)
