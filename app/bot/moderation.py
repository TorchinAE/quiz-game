"""Pending suggestion moderation: approve/reject/edit."""

from .utils import cancel_keyboard, edit_or_reply, menu_keyboard, safe_edit_message


async def handle_moderation(update, context, data: str):
    parts = data.split(":")
    if len(parts) == 1 or (len(parts) == 2 and parts[1].startswith("p")):
        page = int(parts[1][1:]) if len(parts) == 2 and parts[1].startswith("p") else 0
        return await show_pending_list(update, context, page)

    action = parts[1]
    item_id = int(parts[2]) if len(parts) > 2 else None

    if action == "vw":
        return await show_pending_view(update, context, item_id)
    if action == "ap":
        return await execute_approve(update, context, item_id)
    if action == "rj":
        return await execute_reject(update, context, item_id)
    if action == "ed":
        return await start_edit_flow(update, context, item_id)


async def show_pending_list(update, context, page=0):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import SuggestedTopic

    async with async_session() as db:
        result = await db.execute(
            select(SuggestedTopic).where(SuggestedTopic.status == "pending").order_by(SuggestedTopic.created_at.desc())
        )
        topics = list(result.scalars().all())

    def fmt(t):
        return (f"📝 {t.name} (от {t.suggested_by})", f"p:vw:{t.id}")

    from .utils import build_paginated_keyboard

    pg, kb = build_paginated_keyboard(topics, page, fmt, "p", "mn")
    await edit_or_reply(update, context, f"⏳ Модерация ({len(topics)} тем)", reply_markup=kb)


async def show_pending_view(update, context, suggestion_id):
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import SuggestedTopic

    async with async_session() as db:
        result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == suggestion_id))
        topic = result.scalar_one_or_none()

    if not topic:
        await safe_edit_message(update.callback_query, "❌ Не найдено", reply_markup=menu_keyboard("p"))
        return

    text = f"📝 «{topic.name}»\nот {suggested_by}" if (suggested_by := topic.suggested_by) else f"📝 «{topic.name}»"

    rows = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"p:ap:{suggestion_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"p:rj:{suggestion_id}"),
        ],
        [InlineKeyboardButton("✏️ Править", callback_data=f"p:ed:{suggestion_id}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="p"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(rows))


async def execute_approve(update, context, suggestion_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import SuggestedTopic

    async with async_session() as db:
        result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == suggestion_id))
        topic = result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Не найдено", reply_markup=menu_keyboard("p"))
            return
        topic.status = "approved"
        name = topic.name
        await db.commit()

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К модерации", callback_data="p"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await safe_edit_message(update.callback_query, f"✅ Одобрено: «{name}»", reply_markup=kb)


async def execute_reject(update, context, suggestion_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import SuggestedTopic

    async with async_session() as db:
        result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == suggestion_id))
        topic = result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Не найдено", reply_markup=menu_keyboard("p"))
            return
        name = topic.name
        topic.status = "rejected"
        await db.commit()

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К модерации", callback_data="p"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await safe_edit_message(update.callback_query, f"❌ Отклонено: «{name}»", reply_markup=kb)


def start_edit_flow(update, context, suggestion_id):
    context.user_data["flow"] = {
        "type": "suggestion_edit_pending",
        "step": "name",
        "data": {"suggestion_id": suggestion_id},
        "done_callback": f"p:vw:{suggestion_id}",
    }
    return edit_or_reply(
        update,
        context,
        "✏️ Новый текст темы (до 120 символов):",
        reply_markup=cancel_keyboard(f"p:vw:{suggestion_id}"),
    )
