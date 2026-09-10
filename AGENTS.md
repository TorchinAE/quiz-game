# Quiz Game — Project Guide

## Overview

Multiplayer quiz game built with **FastAPI** + **WebSocket** + **SQLAlchemy (async)**. Players join rooms by code, form teams (A vs B, up to 4 per team), and answer 12 timed questions per game. Includes admin panel, Telegram bot integration, and auto-backup.

## Tech Stack

- **Python 3.12+**, FastAPI, Uvicorn
- **SQLAlchemy 2.0** (async) + **aiosqlite** (SQLite)
- **Jinja2** templates + vanilla CSS (no frontend framework)
- **WebSocket** for real-time game state
- **JWT** auth (python-jose + bcrypt/passlib)
- **pytest** + pytest-asyncio + httpx for testing
- **Ruff** for linting (line-length 120, target py312)

## Architecture

```
app/
  main.py           — FastAPI app, lifespan (DB init, CSV load, inactivity checker, Telegram bot, auto-backup)
  config.py         — All settings (env vars + constants)
  database.py       — Async SQLAlchemy engine + session factory
  models.py         — All SQLAlchemy models (Topic, Question, Game, Team, Player, Room, RoomMember, RoomAnswer, etc.)
  auth.py           — JWT helpers, password hashing, admin/team/player auth dependencies
  telegram_bot.py   — Telegram bot integration
  backup.py         — Auto-backup to remote server
  routers/
    auth_router.py  — Player registration/login, guest login, team registration (legacy)
    rooms.py        — Room CRUD, join/leave, start game, submit answer, next question
    game.py         — Legacy global game endpoints (team-based, pre-rooms)
    ws.py           — WebSocket endpoints (/ws/game, /ws/room/{code}) + broadcast helpers
    admin.py        — Admin CRUD (topics, questions, images), stats, backup
    leaderboard.py  — Player leaderboard (top 5)
    suggestions.py  — Topic suggestions with voting
  templates/        — Jinja2 HTML templates (lobby, room, game, admin, results, base)
  static/           — CSS
data/
  questions.csv     — Seed questions loaded on first startup
pictures/           — Uploaded question images (served at /pictures/)
tests/              — pytest test suite
```

## Two Game Systems

1. **Legacy (game.py)** — Global game with 2 teams, admin-controlled. Uses `Game`, `Team`, `TeamAnswer` models.
2. **Rooms (rooms.py)** — Room-based with invite codes. Uses `Room`, `RoomMember`, `RoomAnswer` models. This is the active system.

Both share the same question bank (`Topic` + `Question`).

## Key Patterns

- All DB access is async via `async_session()` context manager or `get_db` dependency
- Auth uses Bearer tokens in `Authorization` header; admin also accepts `admin_token` cookie
- WebSocket broadcasts: `broadcast_*` functions in `ws.py` push state to all connected clients in a room
- `utcnow()` helper strips timezone for SQLite compatibility
- Questions have difficulty 1-3, scoring is `difficulty` points per correct answer (deferred scoring on reveal in rooms)
- Room inactivity auto-closes rooms after 60 seconds (configurable)

## Running

```bash
pip install -r requirements.txt
python run.py          # Starts on port 8080 (configurable via QUIZ_PORT)
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `QUIZ_PORT` | `8080` | Server port |
| `QUIZ_SECRET_KEY` | `super-secret-quiz-key-2024` | JWT secret |
| `QUIZ_DATABASE_URL` | `sqlite+aiosqlite:///./data/quiz.db` | DB URL |
| `QUIZ_TELEGRAM_BOT_TOKEN` | (empty) | Telegram bot token |
| `QUIZ_TELEGRAM_ADMIN_ID` | (empty) | Telegram admin chat ID |
| `QUIZ_BACKUP_*` | (empty) | Backup server config |

## Testing

```bash
pytest                 # Run all tests
pytest --cov=app      # With coverage
```

Tests use `conftest.py` fixtures for async DB setup. Test files mirror routers: `test_rooms.py`, `test_game.py`, `test_admin.py`, `test_auth.py`, `test_ws.py`, etc.

## Linting

```bash
ruff check app/        # Lint
ruff format app/       # Format
```

Config in `pyproject.toml`: rules E, F, I, W; line-length 120; target py312.

## Admin Access

Hardcoded credentials in `config.py`: username `k2k1`, password `123123`. Admin panel at `/admin`.

## Important Notes

- CSV questions are auto-loaded on first startup if DB is empty
- Room codes are 6-char uppercase alphanumeric
- Images stored in `pictures/`, max 5MB, allowed: jpg/jpeg/png/gif/webp/svg
- Telegram bot starts only if `QUIZ_TELEGRAM_BOT_TOKEN` is set
- Auto-backup runs every 7 days (configurable via `QUIZ_BACKUP_INTERVAL_DAYS`)
- No-cache middleware applied to all responses
- Visit tracking middleware logs HTML page visits
