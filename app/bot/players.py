"""Top players management: list, edit, delete."""

from .utils import (
    build_paginated_keyboard,
    cancel_keyboard,
    edit_or_reply,
    menu_keyboard,
    safe_edit_message,
)


async def handle_top_players(update, context, data: str):
    parts = data.split(":")
    if len(parts) == 1 or (len(parts) == 2 and parts[1].startswith("p")):
        page = int(parts[1][1:]) if len(parts) == 2 and parts[1].startswith("p") else 0
        return await show_player_list(update, context, page)

    action = parts[1]
    item_id = int(parts[2]) if len(parts) > 2 else None

    if action == "vw":
        return await show_player_view(update, context, item_id)
    if action == "ed":
        if len(parts) == 4:
            return await start_edit_flow(update, context, item_id, parts[3])
        return await show_edit_picker(update, context, item_id)
    if action == "dl":
        if len(parts) == 4 and parts[3] == "cf":
            return await execute_delete(update, context, item_id)
        return await show_delete_confirm(update, context, item_id)


async def show_player_list(update, context, page=0):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Player

    async with async_session() as db:
        result = await db.execute(select(Player).order_by(Player.total_score.desc()))
        players = list(result.scalars().all())

    def fmt(p):
        return (f"🏆 {p.nickname}: {p.total_score} ({p.games_played} игр)", f"tp:vw:{p.id}")

    pg, kb = build_paginated_keyboard(players, page, fmt, "tp", "mn")
    await edit_or_reply(update, context, f"🏆 Топ игроков ({len(players)})", reply_markup=kb)


async def show_player_view(update, context, player_id):
    from sqlalchemy import select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Player

    async with async_session() as db:
        result = await db.execute(select(Player).where(Player.id == player_id))
        player = result.scalar_one_or_none()

    if not player:
        await safe_edit_message(update.callback_query, "❌ Игрок не найден", reply_markup=menu_keyboard("tp"))
        return

    text = f"🏆 {player.nickname}\n\nОчки: {player.total_score}\nИгр: {player.games_played}\nEmail: {player.email}"

    rows = [
        [
            InlineKeyboardButton("✏️ Очки", callback_data=f"tp:ed:{player_id}:s"),
            InlineKeyboardButton("✏️ Игры", callback_data=f"tp:ed:{player_id}:g"),
        ],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"tp:dl:{player_id}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="tp"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(rows))


async def show_edit_picker(update, context, player_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✏️ Очки", callback_data=f"tp:ed:{player_id}:s")],
        [InlineKeyboardButton("✏️ Кол-во игр", callback_data=f"tp:ed:{player_id}:g")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"tp:vw:{player_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, "Что редактировать?", reply_markup=InlineKeyboardMarkup(rows))


def start_edit_flow(update, context, player_id, field):
    label = "очки" if field == "s" else "количество игр"
    context.user_data["flow"] = {
        "type": "player_edit",
        "step": field,
        "data": {"player_id": player_id},
        "done_callback": f"tp:vw:{player_id}",
    }
    return edit_or_reply(
        update,
        context,
        f"✏️ Новое значение для «{label}» (число):",
        reply_markup=cancel_keyboard(f"tp:vw:{player_id}"),
    )


async def show_delete_confirm(update, context, player_id):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"tp:dl:{player_id}:cf")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"tp:vw:{player_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await safe_edit_message(update.callback_query, "⚠️ Удалить игрока?", reply_markup=InlineKeyboardMarkup(rows))


async def execute_delete(update, context, player_id):
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Player

    async with async_session() as db:
        result = await db.execute(select(Player).where(Player.id == player_id))
        player = result.scalar_one_or_none()
        if not player:
            await safe_edit_message(update.callback_query, "❌ Игрок не найден", reply_markup=menu_keyboard("tp"))
            return
        name = player.nickname
        await db.delete(player)
        await db.commit()

    await safe_edit_message(update.callback_query, f"✅ Игрок «{name}» удалён", reply_markup=menu_keyboard("tp"))
