import asyncio
import csv
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import ROOM_INACTIVITY_TIMEOUT_SECONDS
from app.database import async_session, init_db
from app.models import Question, Room, Topic, VisitStats
from app.routers import admin, auth_router, game, leaderboard, rooms, suggestions, ws


async def load_questions_from_csv():
    """Load questions from CSV if database is empty."""
    async with async_session() as db:
        result = await db.execute(select(Topic))
        if result.scalars().first() is not None:
            return  # Already loaded

        csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "questions.csv")
        if not os.path.exists(csv_path):
            return

        topics_cache: dict[str, Topic] = {}

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                topic_name = row["topic"].strip()
                if topic_name not in topics_cache:
                    topic = Topic(name=topic_name)
                    db.add(topic)
                    await db.flush()
                    topics_cache[topic_name] = topic

                question = Question(
                    topic_id=topics_cache[topic_name].id,
                    text=row["question"].strip(),
                    image_url=row.get("image_url", "").strip(),
                    option_a=row["option_a"].strip(),
                    option_b=row["option_b"].strip(),
                    option_c=row["option_c"].strip(),
                    option_d=row["option_d"].strip(),
                    correct_option=row["correct"].strip().upper(),
                    explanation=row.get("explanation", "").strip(),
                    difficulty=int(row.get("difficulty", 1)),
                )
                db.add(question)

        await db.commit()


async def inactivity_checker():
    """Background task that closes inactive rooms."""
    from datetime import datetime, timedelta, timezone

    while True:
        try:
            await asyncio.sleep(10)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cutoff = now - timedelta(seconds=ROOM_INACTIVITY_TIMEOUT_SECONDS)
            async with async_session() as db:
                result = await db.execute(
                    select(Room).where(
                        Room.status.in_(["waiting", "active"]),
                        Room.last_activity_at < cutoff,
                    )
                )
                inactive_rooms = result.scalars().all()
                for room in inactive_rooms:
                    room.status = "finished"
                    db.add(room)
                    await db.commit()
                    # Broadcast room closed
                    from app.routers.ws import broadcast_room_closed

                    await broadcast_room_closed(room.code)
        except Exception:
            pass


async def log_visit(page: str, request: Request):
    """Log a page visit asynchronously."""
    try:
        nickname = request.cookies.get("player_nickname")
        async with async_session() as db:
            visit = VisitStats(page=page, player_nickname=nickname)
            db.add(visit)
            await db.commit()
    except Exception:
        pass


class VisitTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            path = request.url.path
            if path in ("/", "/lobby"):
                page = "lobby"
            elif path.startswith("/room/"):
                page = "room"
            elif path == "/admin":
                page = "admin"
            else:
                page = path
            asyncio.create_task(log_visit(page, request))
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await load_questions_from_csv()
    inactivity_task = asyncio.create_task(inactivity_checker())

    from app.config import TELEGRAM_BOT_TOKEN
    from app.telegram_bot import start_bot, stop_bot

    bot_task = None
    if TELEGRAM_BOT_TOKEN:
        bot_task = asyncio.create_task(start_bot())

    from app.backup import auto_backup_loop

    backup_task = asyncio.create_task(auto_backup_loop())

    yield

    inactivity_task.cancel()
    backup_task.cancel()
    if bot_task:
        await stop_bot()


app = FastAPI(title="Quiz Game", lifespan=lifespan)


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)
app.add_middleware(VisitTrackingMiddleware)

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
pictures_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pictures")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/pictures", StaticFiles(directory=pictures_dir), name="pictures")

app.include_router(auth_router.router)
app.include_router(admin.router)
app.include_router(game.router)
app.include_router(ws.router)
app.include_router(rooms.router)
app.include_router(leaderboard.router)
app.include_router(suggestions.router)


# --- Page routes ---
templates = Jinja2Templates(directory=templates_dir)


@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return templates.TemplateResponse("lobby.html", {"request": request})


@app.get("/lobby", response_class=HTMLResponse)
async def page_lobby(request: Request):
    return templates.TemplateResponse("lobby.html", {"request": request})


@app.get("/room/{room_code}", response_class=HTMLResponse)
async def page_room(request: Request, room_code: str):
    return templates.TemplateResponse("room.html", {"request": request, "room_code": room_code})


@app.get("/game", response_class=HTMLResponse)
async def page_game(request: Request):
    return templates.TemplateResponse("game.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def page_admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/results", response_class=HTMLResponse)
async def page_results(request: Request):
    return templates.TemplateResponse("results.html", {"request": request})
