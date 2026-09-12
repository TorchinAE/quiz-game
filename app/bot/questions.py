"""Questions CRUD handlers with image management."""

import logging
import os

from .utils import (
    build_paginated_keyboard,
    cancel_keyboard,
    edit_or_reply,
    menu_keyboard,
    safe_edit_message,
)

logger = logging.getLogger(__name__)

PICTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "pictures")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


async def handle_questions(update, context, data: str):
    parts = data.split(":")
    if len(parts) >= 2 and parts[1] not in ("vw", "ed", "dl", "tog", "cr", "tp", "img"):
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
    if action == "img":
        return await handle_image_action(update, context, parts)


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
                    select(func.count(Question.id)).where(
                        Question.topic_id == t.id,
                        Question.is_active == True,  # noqa: E712
                    )
                )
            ).scalar() or 0
            counts[t.id] = cnt

    def fmt(t):
        return (f"{t.name} ({counts.get(t.id, 0)})", f"q:{t.id}")

    pg, kb = build_paginated_keyboard(topics, 0, fmt, "q:tp", "mn")
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
        img = "🖼" if q.image_url else "  "
        short = q.text[:35] + ("..." if len(q.text) > 35 else "")
        return (f"{s}{img} {short}", f"q:vw:{q.id}")

    extra = [[InlineKeyboardButton("➕ Создать вопрос", callback_data=f"q:cr:{topic_id}")]]
    pg, kb = build_paginated_keyboard(questions, page, fmt, f"q:{topic_id}", "q", extra)
    await safe_edit_message(update.callback_query, f"❓ {topic.name} — {len(questions)} вопросов", reply_markup=kb)


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
    img_status = f"🖼 {q.image_url}" if q.image_url else "🖼 Нет"
    text = (
        f"{status} Вопрос #{q.id}\n"
        f"Тема: {q.topic.name if q.topic else '?'}\n\n"
        f"{q.text}\n\n"
        f"A: {q.option_a}\nB: {q.option_b}\nC: {q.option_c}\nD: {q.option_d}\n\n"
        f"Ответ: {q.correct_option} | Сложность: {diff}\n"
        f"Пояснение: {q.explanation or '—'}\n"
        f"Картинка: {img_status}"
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
        [InlineKeyboardButton("🖼 Картинка", callback_data=f"q:img:{question_id}")],
        [InlineKeyboardButton("🔄 Вкл/Выкл", callback_data=f"q:tog:{question_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"q:dl:{question_id}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"q:{topic_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]

    # Send image preview if exists, then the text with buttons
    query = update.callback_query
    if q.image_url:
        try:
            photo = None
            if q.image_url.startswith("http"):
                photo = q.image_url
            else:
                # Local file — read from disk
                rel = q.image_url.lstrip("/")
                if rel.startswith("pictures/"):
                    rel = rel[len("pictures/") :]
                local_path = os.path.join(PICTURES_DIR, rel)
                if os.path.isfile(local_path):
                    photo = open(local_path, "rb")

            if photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                )
                if hasattr(photo, "close"):
                    photo.close()
        except Exception as e:
            logger.warning(f"Failed to send photo: {e}")
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(rows))


# --- Image management ---


async def handle_image_action(update, context, parts):
    """Handle image-related callbacks: q:img:{id}, q:img:{id}:browse, q:img:{id}:url,
    q:img:{id}:del, q:img:{id}:del:cf, q:img:{id}:sel:{page}, q:img:{id}:pick:{filename}."""
    question_id = int(parts[2])

    if len(parts) == 3:
        # q:img:{id} — show image menu
        return await show_image_menu(update, context, question_id)

    sub_action = parts[3]

    if sub_action == "url":
        return await start_image_url_flow(update, context, question_id)
    if sub_action == "upload":
        return await start_image_upload_flow(update, context, question_id)
    if sub_action == "browse":
        return await show_image_browser(update, context, question_id, 0)
    if sub_action == "sel":
        page = int(parts[4]) if len(parts) > 4 else 0
        return await show_image_browser(update, context, question_id, page)
    if sub_action == "pick":
        filename = parts[4]
        return await execute_image_pick(update, context, question_id, filename)
    if sub_action == "del":
        if len(parts) > 4 and parts[4] == "cf":
            return await execute_image_clear(update, context, question_id)
        return await show_image_delete_confirm(update, context, question_id)


async def show_image_menu(update, context, question_id):
    """Show image management options."""
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Question

    async with async_session() as db:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()

    if not q:
        await safe_edit_message(update.callback_query, "❌ Вопрос не найден", reply_markup=menu_keyboard("q"))
        return

    current = q.image_url or "Нет"
    text = f"🖼 Картинка вопроса #{question_id}\n\nТекущая: {current}"

    rows = [
        [InlineKeyboardButton("📝 Ввести URL", callback_data=f"q:img:{question_id}:url")],
        [InlineKeyboardButton("📤 Загрузить фото", callback_data=f"q:img:{question_id}:upload")],
        [InlineKeyboardButton("📂 Выбрать из каталога", callback_data=f"q:img:{question_id}:browse")],
    ]
    if q.image_url:
        rows.append([InlineKeyboardButton("🗑 Удалить картинку", callback_data=f"q:img:{question_id}:del")])
    rows.append(
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"q:vw:{question_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ]
    )
    await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(rows))


def start_image_url_flow(update, context, question_id):
    """Start text input flow for image URL."""
    context.user_data["flow"] = {
        "type": "question_edit",
        "step": "i",
        "data": {"question_id": question_id},
        "done_callback": f"q:vw:{question_id}",
    }
    return edit_or_reply(
        update,
        context,
        "🖼 Введите URL картинки\n(или «-» чтобы очистить):",
        reply_markup=cancel_keyboard(f"q:img:{question_id}"),
    )


def start_image_upload_flow(update, context, question_id):
    """Ask admin to send a photo."""
    context.user_data["flow"] = {
        "type": "question_image_upload",
        "step": "photo",
        "data": {"question_id": question_id},
        "done_callback": f"q:vw:{question_id}",
    }
    return edit_or_reply(
        update,
        context,
        "🖼 Отправьте фото следующим сообщением\n(или «отмена» для отмены):",
        reply_markup=cancel_keyboard(f"q:img:{question_id}"),
    )


async def show_image_browser(update, context, question_id, page=0):
    """Browse images from pictures/ directory."""
    os.makedirs(PICTURES_DIR, exist_ok=True)
    files = []
    for f in sorted(os.listdir(PICTURES_DIR)):
        ext = os.path.splitext(f)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            files.append(f)

    def fmt(f):
        return (f"🖼 {f}", f"q:img:{question_id}:pick:{f}")

    pg, kb = build_paginated_keyboard(files, page, fmt, f"q:img:{question_id}:sel", f"q:img:{question_id}")
    await safe_edit_message(
        update.callback_query,
        f"📂 Каталог картинок ({len(files)} файлов)\nВыберите файл:",
        reply_markup=kb,
    )


async def execute_image_pick(update, context, question_id, filename):
    """Set selected image as question image."""
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Question

    url = f"/pictures/{filename}"

    async with async_session() as db:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if not q:
            await safe_edit_message(update.callback_query, "❌ Вопрос не найден", reply_markup=menu_keyboard("q"))
            return
        q.image_url = url
        await db.commit()

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К вопросу", callback_data=f"q:vw:{question_id}"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await safe_edit_message(update.callback_query, f"✅ Картинка установлена:\n{url}", reply_markup=kb)


async def show_image_delete_confirm(update, context, question_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"q:img:{question_id}:del:cf")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"q:img:{question_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(
        update.callback_query, "⚠️ Удалить картинку из вопроса?", reply_markup=InlineKeyboardMarkup(rows)
    )


async def execute_image_clear(update, context, question_id):
    """Clear image_url from question."""
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Question

    async with async_session() as db:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if not q:
            await safe_edit_message(update.callback_query, "❌ Вопрос не найден", reply_markup=menu_keyboard("q"))
            return
        q.image_url = ""
        await db.commit()

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К вопросу", callback_data=f"q:vw:{question_id}"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await safe_edit_message(update.callback_query, "✅ Картинка удалена", reply_markup=kb)


# --- Create / Edit / Delete / Toggle ---


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
    labels = {
        "t": "текст",
        "o": "правильный ответ (A/B/C/D)",
        "e": "пояснение",
        "f": "сложность (1/2/3)",
        "i": "URL изображения",
    }
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
        [InlineKeyboardButton("🖼 Картинка", callback_data=f"q:img:{question_id}")],
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
