"""Questions CRUD handlers."""

import logging

from .utils import (
    build_paginated_keyboard,
    cancel_keyboard,
    edit_or_reply,
    menu_keyboard,
    safe_edit_message,
)

logger = logging.getLogger(__name__)


async def handle_questions(update, context, data: str):
    parts = data.split(":")
    # q:topic_id or q:topic_id:pN
    if len(parts) >= 2 and parts[1] not in ("vw", "ed", "dl", "tog", "cr", "tp"):
        topic_id = int(parts[1])
        page = int(parts[2][1:]) if len(parts) > 2 and parts[2].startswith("p") else 0
        return await show_question_list(update, context, topic_id, page)

    if len(parts) == 1:
        return await show_topic_picker(update, context)

    action = parts[1]
    item_id = int(parts[2]) if len(parts) > 2 else None

    if action == "tp":
        return await show_topic_picker(update, context)
    if action == "vw":
        return await show_question_view(update, context, item_id)
    if action == "cr":
        return await start_create_flow(update, context, item_id)
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


async def show_topic_picker(update, context):
    from sqlalchemy import func, select

    from app.database import async_session
    from app.models import Question, Topic

    async with async_session() as db:
        result = await db.execute(select(Topic).where(Topic.is_active == True).order_by(Topic.id))  # noqa: E712
        topics = list(result.scalars().all())
        counts = {}
        for t in topics:
            cnt = (
                await db.execute(
                    select(func.count(Question.id)).where(Question.topic_id == t.id, Question.is_active == True)  # noqa: E712
                )
            ).scalar() or 0
            counts[t.id] = cnt

    def fmt(t):
        return (f"{t.name} ({counts.get(t.id, 0)})", f"q:{t.id}")

    extra = None
    pg, kb = build_paginated_keyboard(topics, 0, fmt, "q:tp", "mn", extra)
    await edit_or_reply(update, context, "❓ Выберите тему:", reply_markup=kb)


async def show_question_list(update, context, topic_id, page=0):
    from sqlalchemy import select
    from telegram import InlineKeyboardButton

    from app.database import async_session
    from app.models import Question, Topic

    async with async_session() as db:
        t_result = await db.execute(select(Topic).where(Topic.id == topic_id))
        topic = t_result.scalar_one_or_none()
        if not topic:
            await safe_edit_message(update.callback_query, "❌ Тема не найдена", reply_markup=menu_keyboard("q"))
            return
        q_result = await db.execute(select(Question).where(Question.topic_id == topic_id).order_by(Question.id))
        questions = list(q_result.scalars().all())

    def fmt(q):
        s = "🟢" if q.is_active else "🔴"
        short = q.text[:40] + ("..." if len(q.text) > 40 else "")
        return (f"{s} {short}", f"q:vw:{q.id}")

    extra = [[InlineKeyboardButton("➕ Создать вопрос", callback_data=f"q:cr:{topic_id}")]]
    pg, kb = build_paginated_keyboard(questions, page, fmt, f"q:{topic_id}", "q", extra)
    await safe_edit_message(
        update.callback_query,
        f"❓ {topic.name} — {len(questions)} вопросов",
        reply_markup=kb,
    )


async def show_question_view(update, context, question_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models import Question

    async with async_session() as db:
        result = await db.execute(
            select(Question).options(selectinload(Question.topic)).where(Question.id == question_id)
        )
        q = result.scalar_one_or_none()

    if not q:
        await safe_edit_message(update.callback_query, "❌ Вопрос не найден", reply_markup=menu_keyboard("q"))
        return

    status = "🟢" if q.is_active else "🔴"
    diff = "⭐" * q.difficulty
    text = (
        f"{status} Вопрос #{q.id}\n"
        f"Тема: {q.topic.name if q.topic else '?'}\n\n"
        f"{q.text}\n\n"
        f"A: {q.option_a}\nB: {q.option_b}\nC: {q.option_c}\nD: {q.option_d}\n\n"
        f"Ответ: {q.correct_option} | Сложность: {diff}\n"
        f"Пояснение: {q.explanation or '—'}"
    )

    topic_id = q.topic_id
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [
            InlineKeyboardButton("✏️ Текст", callback_data=f"q:ed:{question_id}:t"),
            InlineKeyboardButton("✏️ Ответ", callback_data=f"q:ed:{question_id}:o"),
        ],
        [
            InlineKeyboardButton("✏️ Объяснение", callback_data=f"q:ed:{question_id}:e"),
            InlineKeyboardButton("✏️ Сложность", callback_data=f"q:ed:{question_id}:f"),
        ],
        [InlineKeyboardButton("🔄 Вкл/Выкл", callback_data=f"q:tog:{question_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"q:dl:{question_id}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"q:{topic_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(rows))


def start_create_flow(update, context, topic_id):
    context.user_data["flow"] = {
        "type": "question_create",
        "step": "text",
        "data": {"topic_id": topic_id},
        "done_callback": f"q:{topic_id}",
    }
    return edit_or_reply(
        update,
        context,
        "📝 Создание вопроса\n\nШаг 1/9: Текст вопроса:",
        reply_markup=cancel_keyboard(f"q:{topic_id}"),
    )


def start_edit_flow(update, context, question_id, field):
    labels = {"t": "текст", "o": "правильный ответ (A/B/C/D)", "e": "пояснение", "f": "сложность (1/2/3)"}
    context.user_data["flow"] = {
        "type": "question_edit",
        "step": field,
        "data": {"question_id": question_id},
        "done_callback": f"q:vw:{question_id}",
    }
    return edit_or_reply(
        update,
        context,
        f"✏️ Новое значение для «{labels.get(field, field)}»:",
        reply_markup=cancel_keyboard(f"q:vw:{question_id}"),
    )


async def show_edit_picker(update, context, question_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✏️ Текст", callback_data=f"q:ed:{question_id}:t")],
        [InlineKeyboardButton("✏️ Ответ", callback_data=f"q:ed:{question_id}:o")],
        [InlineKeyboardButton("✏️ Объяснение", callback_data=f"q:ed:{question_id}:e")],
        [InlineKeyboardButton("✏️ Сложность", callback_data=f"q:ed:{question_id}:f")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"q:vw:{question_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, "Что редактировать?", reply_markup=InlineKeyboardMarkup(rows))


async def show_delete_confirm(update, context, question_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"q:dl:{question_id}:cf")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"q:vw:{question_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, "⚠️ Удалить вопрос?", reply_markup=InlineKeyboardMarkup(rows))


async def execute_delete(update, context, question_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Question

    async with async_session() as db:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if not q:
            await safe_edit_message(update.callback_query, "❌ Вопрос не найден", reply_markup=menu_keyboard("q"))
            return
        topic_id = q.topic_id
        await db.delete(q)
        await db.commit()

    await safe_edit_message(
        update.callback_query,
        f"✅ Вопрос #{question_id} удалён",
        reply_markup=menu_keyboard(f"q:{topic_id}"),
    )


async def execute_toggle(update, context, question_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Question

    async with async_session() as db:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if not q:
            await safe_edit_message(update.callback_query, "❌ Вопрос не найден", reply_markup=menu_keyboard("q"))
            return
        q.is_active = not q.is_active
        await db.commit()

    await show_question_view(update, context, question_id)
