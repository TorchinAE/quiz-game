# Quiz Game — Agent Guide

## What it is

Multiplayer quiz game. FastAPI + SQLAlchemy async + SQLite + Jinja2 + WebSocket. Russian UI, dark theme. Running behind nginx at `/quiz/` on port 8080.

## Commands

```bash
# Activate venv first
source venv/bin/activate

# Lint + format (REQUIRED before every commit and push)
ruff check app/ --fix
ruff format .

# Run tests
pytest -x -q
pytest tests/test_auth.py -x -q          # single file
pytest tests/test_auth.py::test_name -x  # single test

# Start server
python run.py                             # port 8080 (QUIZ_PORT)
```

**CI runs `ruff check .` and `ruff format --check .` on push to `quiz-game`.** Fix all lint/format errors before pushing or CI fails.

## Architecture

Two game systems coexist:
- **Rooms** (`routers/rooms.py`) — active. Room codes, teams A/B, WebSocket real-time. Models: `Room`, `RoomMember`, `RoomAnswer`.
- **Legacy** (`routers/game.py`) — old global game. Models: `Game`, `Team`, `TeamAnswer`. Still in codebase.

Shared: `Topic` + `Question` question bank, loaded from `data/questions.csv` on first startup.

Key files:
- `app/main.py` — lifespan (DB init, CSV load, inactivity checker, bot, backup), middleware, page routes
- `app/config.py` — all settings from env vars. Admin creds from `QUIZ_ADMIN_USERNAME`/`QUIZ_ADMIN_PASSWORD`
- `app/auth.py` — JWT create/verify, `get_current_player`/`get_current_team`/`verify_admin` dependencies
- `app/routers/ws.py` — WebSocket `/ws/room/{code}`, `broadcast_*` helpers for room events
- `app/database.py` — async engine, `init_db()` with inline migrations (ALTER TABLE if column missing)
- `app/templates/lobby.html` — main page, auth, room list, create room, topic cards, suggestions
- `app/templates/room.html` — game room, timer, answer, reveal, WebSocket events

## Key patterns

- All DB access async: `async_session()` or `get_db` dependency
- `utcnow()` strips timezone for SQLite compatibility
- Scoring is deferred: answers stored on submit, scores calculated on reveal in `broadcast_reveal_to_room`
- Questions have difficulty 1-3; score = difficulty points per correct answer
- `fetchAuth(url, options)` in templates — wraps fetch, auto-logout on 401
- `showToast(msg, type)` — floating notification (success/error)
- Room inactivity auto-closes after 60s (`ROOM_INACTIVITY_TIMEOUT_SECONDS`)
- `loadState()` called on page load (not just on WebSocket open)
- Answer is auto-submitted when timer expires (no manual submit button)

## Secrets & deploy

- Admin creds: `QUIZ_ADMIN_USERNAME`, `QUIZ_ADMIN_PASSWORD` in `.env` (not in repo, in `.gitignore`)
- Systemd service: `/etc/systemd/system/quiz-game.service` with `EnvironmentFile=/home/mi/quiz-game/.env`
- CI workflow (`.github/workflows/ci.yml`) writes GitHub Secrets to `.env` on deploy via SSH
- `quiz-game.service` file in repo root — copied to systemd on deploy

## Nginx

Config at `nginx/quiz-game.conf`, deployed to `/etc/nginx/sites-available/`. Proxies `/quiz/` → `http://127.0.0.1:8080/`. WebSocket headers + 86400s timeout. Static: `/quiz/static/` and `/quiz/pictures/` proxied separately.

## Testing quirks

- `conftest.py` sets env vars for test DB and admin creds before importing app
- Test DB: `data/test_quiz.db` — auto-created/dropped per test via `create_all`/`drop_all`
- Delete stale test DB manually if schema changes: `rm data/test_quiz.db`
- `asyncio_mode = "auto"` in pyproject.toml — no need for `@pytest.mark.asyncio` decorator

## Gotchas

- `navigator.clipboard` doesn't work on HTTP — use textarea+execCommand fallback for copy
- QR codes generated via `api.qrserver.com` (external API, no deps)
- Private rooms filtered from public list (`Room.is_private == False`)
- `SECRET_KEY` default is insecure — must be set via env var in production
