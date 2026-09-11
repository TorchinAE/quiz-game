"""Statistics with period filters."""

from .utils import edit_or_reply


async def handle_stats(update, context, data: str):
    parts = data.split(":")
    period = parts[1] if len(parts) > 1 else "all"
    await show_stats(update, context, period)


async def show_stats(update, context, period="all"):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.database import async_session
    from app.models import Player, Room, VisitStats

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = None
    period_label = "За всё время"

    if period == "t":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Сегодня"
    elif period == "m":
        cutoff = now - timedelta(days=30)
        period_label = "За месяц"
    elif period == "y":
        cutoff = now - timedelta(days=365)
        period_label = "За год"

    async with async_session() as db:
        qv = select(func.count(VisitStats.id))
        qp = select(func.count(Player.id))
        qr = select(func.count(Room.id))
        qg = select(func.count(Room.id)).where(Room.status == "finished")

        if cutoff:
            qv = qv.where(VisitStats.visited_at >= cutoff)
            qp = qp.where(Player.created_at >= cutoff)
            qr = qr.where(Room.created_at >= cutoff)
            qg = qg.where(Room.created_at >= cutoff)

        visits = (await db.execute(qv)).scalar() or 0
        players = (await db.execute(qp)).scalar() or 0
        rooms = (await db.execute(qr)).scalar() or 0
        games = (await db.execute(qg)).scalar() or 0

        # Total counts for growth calculation
        total_players = (await db.execute(select(func.count(Player.id)))).scalar() or 0

    growth = f"+{players}" if period != "all" else f"{total_players}"
    if period != "all":
        growth = f"{players} (рост: +{players})"

    text = (
        f"📊 Статистика — {period_label}\n\n"
        f"Посещений: {visits}\n"
        f"Игроков: {growth}\n"
        f"Комнат: {rooms}\n"
        f"Игр завершено: {games}\n"
        f"Всего игроков в базе: {total_players}"
    )

    rows = [
        [
            InlineKeyboardButton(f"{'📌 ' if period == 't' else ''}Сегодня", callback_data="s:t"),
            InlineKeyboardButton(f"{'📌 ' if period == 'm' else ''}Месяц", callback_data="s:m"),
        ],
        [
            InlineKeyboardButton(f"{'📌 ' if period == 'y' else ''}Год", callback_data="s:y"),
            InlineKeyboardButton(f"{'📌 ' if period == 'all' else ''}Всё", callback_data="s"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="mn"),
            InlineKeyboardButton("🏠 Меню", callback_data="mn"),
        ],
    ]
    await edit_or_reply(update, context, text, reply_markup=InlineKeyboardMarkup(rows))
