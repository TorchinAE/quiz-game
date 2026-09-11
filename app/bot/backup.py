"""Backup trigger handler."""

import logging

from .utils import safe_edit_message

logger = logging.getLogger(__name__)


async def handle_backup(update, context, data: str):
    parts = data.split(":")
    if len(parts) > 1 and parts[1] == "cf":
        return await execute_backup(update, context)
    return await show_backup_confirm(update, context)


async def show_backup_confirm(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("💾 Создать бэкап", callback_data="bk:cf")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="mn"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, "💾 Бэкап", reply_markup=InlineKeyboardMarkup(rows))


async def execute_backup(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    await safe_edit_message(update.callback_query, "⏳ Создаю бэкап...")

    try:
        from app.backup import create_backup, upload_backup

        path = await create_backup()
        uploaded = await upload_backup(path)
        status = "загружен на сервер" if uploaded else "сохранён локально"
        text = f"✅ Бэкап {status}:\n{path}"
    except Exception as e:
        logger.exception("Backup failed")
        text = f"❌ Ошибка: {e}"

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ Назад", callback_data="bk"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await safe_edit_message(update.callback_query, text, reply_markup=kb)
