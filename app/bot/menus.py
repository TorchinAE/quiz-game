"""Main menu rendering."""

from .constants import MENU_TITLE
from .utils import _is_admin, safe_edit_message


async def cmd_start(update, context):
    """Handle /start command — show main menu."""
    if not _is_admin(update):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await _render_menu_message(update.message.reply_text)


async def show_main_menu(update, context, data=""):
    """Render main menu from callback."""
    await _render_menu_edit(update.callback_query)


async def _render_menu_message(send_fn):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = [
        [InlineKeyboardButton("📚 Темы", callback_data="t"), InlineKeyboardButton("❓ Вопросы", callback_data="q")],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="s"),
            InlineKeyboardButton("🗳️ Голосование", callback_data="v"),
        ],
        [
            InlineKeyboardButton("⏳ Модерация", callback_data="p"),
            InlineKeyboardButton("🏆 Топ игроков", callback_data="tp"),
        ],
        [InlineKeyboardButton("💾 Бэкап", callback_data="bk")],
    ]
    await send_fn(MENU_TITLE, reply_markup=InlineKeyboardMarkup(buttons))


async def _render_menu_edit(query):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = [
        [InlineKeyboardButton("📚 Темы", callback_data="t"), InlineKeyboardButton("❓ Вопросы", callback_data="q")],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="s"),
            InlineKeyboardButton("🗳️ Голосование", callback_data="v"),
        ],
        [
            InlineKeyboardButton("⏳ Модерация", callback_data="p"),
            InlineKeyboardButton("🏆 Топ игроков", callback_data="tp"),
        ],
        [InlineKeyboardButton("💾 Бэкап", callback_data="bk")],
    ]
    await safe_edit_message(query, MENU_TITLE, reply_markup=InlineKeyboardMarkup(buttons))
