"""Voting suggestions CRUD (approved topics)."""

from .utils import (
    build_paginated_keyboard,
    cancel_keyboard,
    edit_or_reply,
    menu_keyboard,
    safe_edit_message,
)


async def handle_suggestions(update, context, data: str):
    parts = data.split(":")
    if len(parts) == 1 or (len(parts) == 2 and parts[1].startswith("p")):
        page = int(parts[1][1:]) if len(parts) == 2 and parts[1].startswith("p") else 0
        return await show_suggestion_list(update, context, page)

    action = parts[1]
    item_id = int(parts[2]) if len(parts) > 2 else None

    if action == "vw":
        return await show_suggestion_view(update, context, item_id)
    if action == "cr":
        return await start_create_flow(update, context)
    if action == "ed":
        return await start_edit_flow(update, context, item_id)
    if action == "dl":
        if len(parts) == 4 and parts[3] == "cf":
            return await execute_delete(update, context, item_id)
        return await show_delete_confirm(update, context, item_id)


async def show_suggestion_list(update, context, page=0):
    from sqlalchemy import func, select
    from telegram import InlineKeyboardButton

    from app.database import async_session
    from app.models import SuggestedTopic, TopicVote

    async with async_session() as db:
        result = await db.execute(
            select(
                SuggestedTopic,
                func.coalesce(func.sum(TopicVote.vote), 0).label("rating"),
            )
            .outerjoin(TopicVote)
            .where(SuggestedTopic.status == "approved")
            .group_by(SuggestedTopic.id)
            .order_by(func.coalesce(func.sum(TopicVote.vote), 0).desc())
        )
        items = [(t, r) for t, r in result.all()]

    def fmt(pair):
        t, r = pair
        sign = "+" if r > 0 else ""
        return (f"{sign}{r} — {t.name}", f"v:vw:{t.id}")

    extra = [[InlineKeyboardButton("➕ Добавить тему", callback_data="v:cr")]]
    pg, kb = build_paginated_keyboard(items, page, fmt, "v", "mn", extra)
    await edit_or_reply(update, context, f"🗳️ Голосование ({len(items)} тем)", reply_markup=kb)


async def show_suggestion_view(update, context, suggestion_id):
    from sqlalchemy import func, select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import SuggestedTopic, TopicVote

    async with async_session() as db:
        result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == suggestion_id))
        topic = result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Не найдено", reply_markup=menu_keyboard("v"))
            return
        rating = (
            await db.execute(
                select(func.coalesce(func.sum(TopicVote.vote), 0)).where(TopicVote.suggested_topic_id == suggestion_id)
            )
        ).scalar() or 0

    sign = "+" if rating > 0 else ""
    text = f"🗳️ «{topic.name}»\n\nПредложил: {topic.suggested_by}\nРейтинг: {sign}{rating}"

    rows = [
        [InlineKeyboardButton("✏️ Править", callback_data=f"v:ed:{suggestion_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"v:dl:{suggestion_id}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="v"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(rows))


def start_create_flow(update, context):
    context.user_data["flow"] = {
        "type": "suggestion_create",
        "step": "name",
        "data": {},
        "done_callback": "v",
    }
    text = "🗳️ Новая тема голосования\n\nНазвание (до 120 символов):"
    return edit_or_reply(update, context, text, reply_markup=cancel_keyboard("v"))


def start_edit_flow(update, context, suggestion_id):
    context.user_data["flow"] = {
        "type": "suggestion_edit",
        "step": "name",
        "data": {"suggestion_id": suggestion_id},
        "done_callback": f"v:vw:{suggestion_id}",
    }
    return edit_or_reply(
        update,
        context,
        "✏️ Новое название темы (до 120 символов):",
        reply_markup=cancel_keyboard(f"v:vw:{suggestion_id}"),
    )


async def show_delete_confirm(update, context, suggestion_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"v:dl:{suggestion_id}:cf")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"v:vw:{suggestion_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(
        update.callback_query,
        "⚠️ Удалить тему голосования?",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def execute_delete(update, context, suggestion_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import SuggestedTopic

    async with async_session() as db:
        result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == suggestion_id))
        topic = result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Не найдено", reply_markup=menu_keyboard("v"))
            return
        name = topic.name
        await db.delete(topic)
        await db.commit()

    await safe_edit_message(update.callback_query, f"✅ «{name}» удалена", reply_markup=menu_keyboard("v"))
