"""Topics CRUD handlers."""

import logging

from .utils import (
    build_paginated_keyboard,
    cancel_keyboard,
    edit_or_reply,
    menu_keyboard,
    safe_edit_message,
)

logger = logging.getLogger(__name__)


async def handle_topics(update, context, data: str):
    parts = data.split(":")
    if len(parts) == 1 or (len(parts) == 2 and parts[1].startswith("p")):
        page = int(parts[1][1:]) if len(parts) == 2 and parts[1].startswith("p") else 0
        return await show_topic_list(update, context, page)

    action = parts[1]
    item_id = int(parts[2]) if len(parts) > 2 else None

    if action == "vw":
        return await show_topic_view(update, context, item_id)
    if action == "cr":
        return await start_create_flow(update, context)
    if action == "ed":
        if len(parts) == 3:
            return await show_edit_picker(update, context, item_id)
        return await start_edit_flow(update, context, item_id, parts[3])
    if action == "dl":
        if len(parts) == 4 and parts[3] == "cf":
            return await execute_delete(update, context, item_id)
        return await show_delete_confirm(update, context, item_id)
    if action == "tog":
        return await execute_toggle(update, context, item_id)


async def show_topic_list(update, context, page=0):
    from sqlalchemy import func, select

    from app.database import async_session
    from app.models import Question, Topic

    async with async_session() as db:
        result = await db.execute(select(Topic).order_by(Topic.id))
        topics = list(result.scalars().all())
        counts = {}
        for t in topics:
            cnt = (await db.execute(select(func.count(Question.id)).where(Question.topic_id == t.id))).scalar() or 0
            counts[t.id] = cnt

    def fmt(t):
        s = "🟢" if t.is_active else "🔴"
        c = counts.get(t.id, 0)
        return (f"{s} {t.name} ({c})", f"t:vw:{t.id}")

    from telegram import InlineKeyboardButton

    extra = [[InlineKeyboardButton("➕ Создать тему", callback_data="t:cr")]]
    pg, kb = build_paginated_keyboard(topics, page, fmt, "t", "mn", extra)
    await edit_or_reply(update, context, f"📚 Темы ({len(topics)} шт.)", reply_markup=kb)


async def show_topic_view(update, context, topic_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models import Topic

    async with async_session() as db:
        result = await db.execute(select(Topic).options(selectinload(Topic.questions)).where(Topic.id == topic_id))
        topic = result.scalar_one_or_none()

    if not topic:
        await safe_edit_message(update.callback_query, "❌ Тема не найдена", reply_markup=menu_keyboard("t"))
        return

    q_count = len(topic.questions)
    active = sum(1 for q in topic.questions if q.is_active)
    status = "🟢 Активна" if topic.is_active else "🔴 Выключена"

    text = (
        f"📚 {topic.name}\n\n"
        f"Описание: {topic.description or '—'}\n"
        f"Статус: {status}\n"
        f"Вопросов: {q_count} (активных: {active})"
    )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [
            InlineKeyboardButton("✏️ Название", callback_data=f"t:ed:{topic_id}:n"),
            InlineKeyboardButton("✏️ Описание", callback_data=f"t:ed:{topic_id}:d"),
        ],
        [InlineKeyboardButton("✏️ Картинка", callback_data=f"t:ed:{topic_id}:i")],
        [
            InlineKeyboardButton("🔄 Вкл/Выкл", callback_data=f"t:tog:{topic_id}"),
            InlineKeyboardButton("📋 Вопросы", callback_data=f"q:{topic_id}"),
        ],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"t:dl:{topic_id}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="t"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(rows))


def start_create_flow(update, context):
    context.user_data["flow"] = {
        "type": "topic_create",
        "step": "name",
        "data": {},
        "done_callback": "t",
    }
    return edit_or_reply(update, context, "📝 Создание темы\n\nШаг 1/3: Название:", reply_markup=cancel_keyboard("t"))


def start_edit_flow(update, context, topic_id, field):
    labels = {"n": "название", "d": "описание", "i": "URL изображения"}
    context.user_data["flow"] = {
        "type": "topic_edit",
        "step": field,
        "data": {"topic_id": topic_id},
        "done_callback": f"t:vw:{topic_id}",
    }
    return edit_or_reply(
        update,
        context,
        f"✏️ Новое значение для «{labels.get(field, field)}»:\n(или «-» чтобы очистить)",
        reply_markup=cancel_keyboard(f"t:vw:{topic_id}"),
    )


async def show_edit_picker(update, context, topic_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✏️ Название", callback_data=f"t:ed:{topic_id}:n")],
        [InlineKeyboardButton("✏️ Описание", callback_data=f"t:ed:{topic_id}:d")],
        [InlineKeyboardButton("✏️ Картинка", callback_data=f"t:ed:{topic_id}:i")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"t:vw:{topic_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, "Что редактировать?", reply_markup=InlineKeyboardMarkup(rows))


async def show_delete_confirm(update, context, topic_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"t:dl:{topic_id}:cf")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"t:vw:{topic_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(
        update.callback_query,
        "⚠️ Удалить тему и все вопросы?",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def execute_delete(update, context, topic_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Topic

    async with async_session() as db:
        result = await db.execute(select(Topic).where(Topic.id == topic_id))
        topic = result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Тема не найдена", reply_markup=menu_keyboard("t"))
            return
        name = topic.name
        await db.delete(topic)
        await db.commit()

    await safe_edit_message(update.callback_query, f"✅ Тема «{name}» удалена", reply_markup=menu_keyboard("t"))


async def execute_toggle(update, context, topic_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Topic

    async with async_session() as db:
        result = await db.execute(select(Topic).where(Topic.id == topic_id))
        topic = result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Тема не найдена", reply_markup=menu_keyboard("t"))
            return
        topic.is_active = not topic.is_active
        await db.commit()

    await show_topic_view(update, context, topic_id)
