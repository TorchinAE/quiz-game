"""Multi-step text input flow dispatcher."""

import logging

from .utils import home_keyboard

logger = logging.getLogger(__name__)


async def dispatch_flow_step(update, context, flow: dict):
    """Central dispatcher for all multi-step text input flows."""
    text = update.message.text.strip()

    if text.lower() in ("/cancel", "отмена"):
        del context.user_data["flow"]
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="mn")]])
        await update.message.reply_text("❌ Отменено", reply_markup=kb)
        return

    flow_type = flow["type"]

    if flow_type.startswith("topic"):
        await _handle_topic_flow(update, context, flow, text)
    elif flow_type.startswith("question"):
        await _handle_question_flow(update, context, flow, text)
    elif flow_type.startswith("suggestion"):
        await _handle_suggestion_flow(update, context, flow, text)
    elif flow_type.startswith("player"):
        await _handle_player_flow(update, context, flow, text)
    else:
        del context.user_data["flow"]
        await update.message.reply_text("⚠️ Неизвестный режим", reply_markup=home_keyboard())


async def _handle_topic_flow(update, context, flow, text):

    step = flow["step"]

    if flow["type"] == "topic_create":
        if step == "name":
            if not text or len(text) > 200:
                await update.message.reply_text("⚠ Название от 1 до 200 символов:")
                return
            flow["data"]["name"] = text
            flow["step"] = "desc"
            await update.message.reply_text("📝 Шаг 2/3: Описание\n(или «-» чтобы пропустить):")
            return
        if step == "desc":
            flow["data"]["description"] = "" if text == "-" else text
            flow["step"] = "img"
            await update.message.reply_text("📝 Шаг 3/3: URL изображения\n(или «-» чтобы пропустить):")
            return
        if step == "img":
            flow["data"]["image_url"] = "" if text == "-" else text
            await _commit_topic_create(update, context, flow)
            return

    # Single-field edit
    if flow["type"] == "topic_edit":
        value = "" if text == "-" else text
        topic_id = flow["data"]["topic_id"]
        field = step
        await _commit_topic_edit(update, context, flow, topic_id, field, value)


async def _commit_topic_create(update, context, flow):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Topic

    async with async_session() as db:
        topic = Topic(**flow["data"])
        db.add(topic)
        await db.commit()
        await db.refresh(topic)
        tid = topic.id
        name = topic.name

    del context.user_data["flow"]
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К темам", callback_data="t"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await update.message.reply_text(f"✅ Тема «{name}» создана (ID: {tid})", reply_markup=kb)


async def _commit_topic_edit(update, context, flow, topic_id, field, value):
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Topic

    col_map = {"n": "name", "d": "description", "i": "image_url"}
    col = col_map.get(field)
    if not col:
        del context.user_data["flow"]
        await update.message.reply_text("⚠ Неизвестное поле", reply_markup=home_keyboard())
        return

    async with async_session() as db:
        result = await db.execute(select(Topic).where(Topic.id == topic_id))
        topic = result.scalar_one_or_none()
        if not topic:
            del context.user_data["flow"]
            await update.message.reply_text("❌ Тема не найдена", reply_markup=home_keyboard())
            return
        setattr(topic, col, value)
        await db.commit()

    del context.user_data["flow"]
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К теме", callback_data=f"t:vw:{topic_id}"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await update.message.reply_text("✅ Обновлено", reply_markup=kb)


async def _handle_question_flow(update, context, flow, text):

    step = flow["step"]

    if flow["type"] == "question_create":
        steps_order = ["text", "img", "a", "b", "c", "d", "correct", "expl", "diff"]
        n = len(steps_order)

        if step == "text":
            if not text:
                await update.message.reply_text("⚠ Текст вопроса не может быть пустым:")
                return
            flow["data"]["text"] = text
            flow["step"] = "img"
            await update.message.reply_text(f"📝 Шаг 2/{n}: URL изображения\n(или «-» пропустить):")
            return
        if step == "img":
            flow["data"]["image_url"] = "" if text == "-" else text
            flow["step"] = "a"
            await update.message.reply_text(f"📝 Шаг 3/{len(steps_order)}: Вариант A:")
            return
        if step == "a":
            flow["data"]["option_a"] = text
            flow["step"] = "b"
            await update.message.reply_text(f"📝 Шаг 4/{len(steps_order)}: Вариант B:")
            return
        if step == "b":
            flow["data"]["option_b"] = text
            flow["step"] = "c"
            await update.message.reply_text(f"📝 Шаг 5/{len(steps_order)}: Вариант C:")
            return
        if step == "c":
            flow["data"]["option_c"] = text
            flow["step"] = "d"
            await update.message.reply_text(f"📝 Шаг 6/{len(steps_order)}: Вариант D:")
            return
        if step == "d":
            flow["data"]["option_d"] = text
            flow["step"] = "correct"
            await update.message.reply_text(f"📝 Шаг 7/{len(steps_order)}: Правильный ответ (A/B/C/D):")
            return
        if step == "correct":
            if text.upper() not in ("A", "B", "C", "D"):
                await update.message.reply_text("⚠ Введите A, B, C или D:")
                return
            flow["data"]["correct_option"] = text.upper()
            flow["step"] = "expl"
            await update.message.reply_text(f"📝 Шаг 8/{len(steps_order)}: Пояснение\n(или «-» чтобы пропустить):")
            return
        if step == "expl":
            flow["data"]["explanation"] = "" if text == "-" else text
            flow["step"] = "diff"
            await update.message.reply_text(f"📝 Шаг 9/{len(steps_order)}: Сложность (1/2/3):")
            return
        if step == "diff":
            if text not in ("1", "2", "3"):
                await update.message.reply_text("⚠ Введите 1, 2 или 3:")
                return
            flow["data"]["difficulty"] = int(text)
            await _commit_question_create(update, context, flow)
            return

    # Single-field edit
    if flow["type"] == "question_edit":
        question_id = flow["data"]["question_id"]
        field = step
        await _commit_question_edit(update, context, flow, question_id, field, text)


async def _commit_question_create(update, context, flow):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Question

    async with async_session() as db:
        q = Question(**flow["data"])
        db.add(q)
        await db.commit()
        await db.refresh(q)
        qid = q.id
        tid = q.topic_id

    del context.user_data["flow"]
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К вопросам", callback_data=f"q:{tid}"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await update.message.reply_text(f"✅ Вопрос #{qid} создан", reply_markup=kb)


async def _commit_question_edit(update, context, flow, question_id, field, value):
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Question

    col_map = {"t": "text", "o": "correct_option", "e": "explanation", "f": "difficulty", "i": "image_url"}
    col = col_map.get(field)
    if not col:
        del context.user_data["flow"]
        await update.message.reply_text("⚠ Неизвестное поле", reply_markup=home_keyboard())
        return

    # Validation
    if field == "o" and value.upper() not in ("A", "B", "C", "D"):
        await update.message.reply_text("⚠ Введите A, B, C или D:")
        return
    if field == "f":
        if value not in ("1", "2", "3"):
            await update.message.reply_text("⚠ Введите 1, 2 или 3:")
            return
        value = int(value)

    if field == "o":
        value = value.upper()

    async with async_session() as db:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if not q:
            del context.user_data["flow"]
            await update.message.reply_text("❌ Вопрос не найден", reply_markup=home_keyboard())
            return
        setattr(q, col, value)
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
    await update.message.reply_text("✅ Обновлено", reply_markup=kb)


async def _handle_suggestion_flow(update, context, flow, text):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if not text or len(text) > 120:
        await update.message.reply_text("⚠ Название от 1 до 120 символов:")
        return

    if flow["type"] == "suggestion_create":
        from app.database import async_session
        from app.models import SuggestedTopic

        async with async_session() as db:
            topic = SuggestedTopic(name=text, suggested_by="Admin", status="approved")
            db.add(topic)
            await db.commit()

        del context.user_data["flow"]
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("◀️ К голосованию", callback_data="v"),
                    InlineKeyboardButton("🏠 Меню", callback_data="mn"),
                ]
            ]
        )
        await update.message.reply_text(f"✅ Тема «{text}» добавлена в голосование", reply_markup=kb)
        return

    # Edit (pending or approved)
    suggestion_id = flow["data"]["suggestion_id"]
    from sqlalchemy import select

    from app.database import async_session
    from app.models import SuggestedTopic

    async with async_session() as db:
        result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == suggestion_id))
        topic = result.scalar_one_or_none()
        if not topic:
            del context.user_data["flow"]
            await update.message.reply_text("❌ Не найдено", reply_markup=home_keyboard())
            return
        topic.name = text
        await db.commit()

    done_cb = flow.get("done_callback", "v")
    del context.user_data["flow"]
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ Назад", callback_data=done_cb),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await update.message.reply_text(f"✅ Обновлено: «{text}»", reply_markup=kb)


async def _handle_player_flow(update, context, flow, text):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        value = int(text)
    except ValueError:
        await update.message.reply_text("⚠ Введите число:")
        return

    player_id = flow["data"]["player_id"]
    field = flow["step"]

    from sqlalchemy import select

    from app.database import async_session
    from app.models import Player

    col = "total_score" if field == "s" else "games_played"

    async with async_session() as db:
        result = await db.execute(select(Player).where(Player.id == player_id))
        player = result.scalar_one_or_none()
        if not player:
            del context.user_data["flow"]
            await update.message.reply_text("❌ Игрок не найден", reply_markup=home_keyboard())
            return
        setattr(player, col, value)
        await db.commit()

    del context.user_data["flow"]
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ К игроку", callback_data=f"tp:vw:{player_id}"),
                InlineKeyboardButton("🏠 Меню", callback_data="mn"),
            ]
        ]
    )
    await update.message.reply_text("✅ Обновлено", reply_markup=kb)
