# Quiz Game — Full Feature Implementation Plan

> Generated from deep codebase audit on 2026-06-20.
> Stack: FastAPI + SQLAlchemy async + SQLite + Jinja2 templates + WebSocket + inline JS
> All text in Russian. Dark theme. Inline JS only (no separate .js files). All paths use `BASE` variable.

---

## Phase 1: BLOCKER FIXES (F1) — Commit: "fix: paths, port, CSS behind nginx"

### 1.1 CSS path fix

**Problem**: `base.html` line 7 uses `href="static/style.css"` (relative). On `/quiz/room/XXXXX` this resolves to `/quiz/room/static/style.css` → 404.

**Fix in `app/templates/base.html`**:
```html
<!-- OLD -->
<link rel="stylesheet" href="static/style.css">
<!-- NEW -->
<link rel="stylesheet" href="/static/style.css">
```

However, behind nginx the app lives at `/quiz/`. The nginx config strips the prefix (`/quiz/` → `/`), so the app sees requests at `/`. Therefore `/static/style.css` on the app side becomes `/quiz/static/style.css` externally. But the app mounts static at `/static` (line 115 of main.py), so this works.

**But wait**: all `BASE + '/api/...'` JS calls already append the `/quiz` prefix which nginx strips. The static mount at `/static` in the app doesn't include the `/quiz` prefix. So the nginx config needs a separate location for `/quiz/static/` OR the app needs to mount under a prefix.

**Best fix — no app changes needed**: Add a static location block in nginx that proxies `/quiz/static/` to the app's `/static/`:

```nginx
# Add to nginx/quiz-game.conf
location /quiz/static/ {
    proxy_pass http://127.0.0.1:8080/static/;
    proxy_set_header Host $host;
}
location /quiz/pictures/ {
    proxy_pass http://127.0.0.1:8080/pictures/;
    proxy_set_header Host $host;
}
```

**And fix `base.html`** to use the prefixed path:
```html
<link rel="stylesheet" href="/quiz/static/style.css">
```

Actually, this is fragile if the prefix ever changes. Better approach: use a Jinja2 variable.

**Final approach** — use a relative-to-root path that works both standalone and behind nginx:

In `base.html`, change:
```html
<script>const BASE = '/quiz';</script>
```
to:
```html
<script>const BASE = '/quiz';</script>
<link rel="stylesheet" href="/quiz/static/style.css">
```

But to make it work in both dev (no prefix) and production (with prefix), add nginx locations for static assets as shown above, and keep the CSS link as `/quiz/static/style.css`.

**Files modified**: `app/templates/base.html`, `nginx/quiz-game.conf`

### 1.2 Port mismatch fix

**Problem**: `start.sh` and `run.py` bind to port 8000. Nginx proxies to 8080. CI checks port 8080. The systemd service must be configured to override the port, or there's a live bug.

**Fix**: Change `start.sh` and `run.py` to use port 8080:
```python
# run.py
uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)
```
```bash
# start.sh
python3 -u -c "import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=8080)"
```

**Config approach (cleaner)**: Add `PORT` env var to `app/config.py`:
```python
PORT = int(os.getenv("QUIZ_PORT", "8080"))
```
Then use in run.py/start.sh.

**Files modified**: `app/config.py`, `app/main.py` (optional: run from main), `start.sh`, `run.py`

### 1.3 All hardcoded `/quiz/` paths audit

Currently in templates:
- `room.html` line 8: `<a href="/quiz/" ...>` ← hardcoded, OK (always behind nginx)
- `room.html` line 68: `<a href="/quiz/" ...>` ← OK
- `room.html` line 76: `<a href="/quiz/" ...>` ← OK

All JS already uses `BASE + '/...'` which is correct.

**No changes needed** for JS paths. Template hardcoded paths are OK since the app is always accessed behind nginx.

**Commit scope**: `base.html`, `nginx/quiz-game.conf`, `start.sh`, `run.py`, `app/config.py`

---

## Phase 2: DB Schema Changes (F2) — Commit: "feat: add is_active flags, topic suggestions, voting, visit stats"

### 2.1 Schema changes in `app/models.py`

Add `is_active` to existing tables:

```python
class Topic(Base):
    # ... existing fields ...
    is_active = Column(Boolean, default=True)

class Question(Base):
    # ... existing fields ...
    is_active = Column(Boolean, default=True)
```

Add new tables:

```python
class SuggestedTopic(Base):
    __tablename__ = "suggested_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)  # 120 chars max per F5
    suggested_by = Column(String(100), nullable=False)  # player nickname
    player_id = Column(Integer, nullable=True)  # registered player ID or null for guests
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TopicVote(Base):
    __tablename__ = "topic_votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    suggested_topic_id = Column(Integer, ForeignKey("suggested_topics.id"), nullable=False)
    player_nickname = Column(String(100), nullable=False)
    vote = Column(Integer, nullable=False)  # +1 or -1
    voted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    suggested_topic = relationship("SuggestedTopic")
```

Wait — the spec says `topic_votes` table and voting sidebar with up/down arrows. Let me re-read F5:

> F5: Lobby — topic selection on room create with 'completed' marks, theme suggestion (120 chars), voting sidebar with up/down arrows

So voting is on suggested topics (theme suggestions). Players suggest themes, others vote up/down.

Add unique constraint: one vote per player per suggested topic.

```python
class TopicVote(Base):
    __tablename__ = "topic_votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    suggested_topic_id = Column(Integer, ForeignKey("suggested_topics.id"), nullable=False)
    player_nickname = Column(String(100), nullable=False)
    vote = Column(Integer, nullable=False)  # +1 or -1
    voted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    suggested_topic = relationship("SuggestedTopic", back_populates="votes")

# Add to SuggestedTopic:
    votes = relationship("TopicVote", back_populates="suggested_topic", cascade="all, delete-orphan")
```

Add visit stats table:

```python
class VisitStat(Base):
    __tablename__ = "visit_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page = Column(String(100), nullable=False)  # 'lobby', 'room', 'admin', 'game'
    player_nickname = Column(String(100), nullable=True)
    visited_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    session_duration = Column(Integer, nullable=True)  # seconds, filled on leave
```

### 2.2 Migration in `app/database.py`

Add ALTER TABLE migration logic in `init_db()`:

```python
# After existing migration:
# Add is_active to topics if missing
result = await conn.execute(text("PRAGMA table_info(topics)"))
columns = [row[1] for row in result.fetchall()]
if "is_active" not in columns:
    await conn.execute(text("ALTER TABLE topics ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))

# Add is_active to questions if missing
result = await conn.execute(text("PRAGMA table_info(questions)"))
columns = [row[1] for row in result.fetchall()]
if "is_active" not in columns:
    await conn.execute(text("ALTER TABLE questions ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))

# New tables (suggested_topics, topic_votes, visit_stats) created by create_all
```

### 2.3 Filter inactive items in queries

Update `app/routers/game.py` `list_topics` to only show active topics with active questions:
```python
# Filter: only active topics
result = await db.execute(select(Topic).where(Topic.is_active == True))
```

Update `rooms.py` `start_room_game` to filter active questions:
```python
q_result = await db.execute(
    select(Question).where(Question.topic_id == req.topic_id, Question.is_active == True)
)
```

Update `admin.py` `list_topics` and `list_questions` to include `is_active` in response and support filtering.

**Files modified**: `app/models.py`, `app/database.py`, `app/routers/game.py`, `app/routers/rooms.py`, `app/routers/admin.py`

---

## Phase 3: Admin Redesign (F3) — Commit: "feat: admin sidebar nav, image upload, active toggles, question cards"

### 3.1 Sidebar navigation

Replace flat admin page with sidebar layout:

**Structure of `admin.html`**:
```
+--sidebar--+  +--content area---------------------+
| Темы      |  | (changes based on selected section) |
| Вопросы   |  |                                      |
| Голосов.  |  |                                      |
| Топ-игрок |  |                                      |
| Пользо-ли |  |                                      |
+-----------+  +--------------------------------------+
```

Each sidebar item loads a different section into the content area via JS (no page navigation, all inline).

**Sections**:
1. **Темы** (Topics) — existing topic table + active/inactive toggle
2. **Вопросы** (Questions) — card layout with thumbnails + active/inactive toggle
3. **Голосования** (Voting) — table of suggested topics with vote counts
4. **Топ-игроки** (Top Players) — extend leaderboard to show more
5. **Пользователи** (Users) — list of registered players with stats

### 3.2 Image upload/browse/delete

**New API endpoints in `app/routers/admin.py`**:

```python
@router.post("/api/admin/upload-image")
async def upload_image(request: Request, file: UploadFile = File(...)):
    """Upload image to pictures/ directory."""
    require_admin(request)
    # Validate: only jpg/png, max 5MB
    # Generate filename: q{next_number}.jpg or topic_{id}.jpg
    # Save to pictures/
    # Return {"url": "/pictures/filename.jpg"}
    ...

@router.get("/api/admin/images")
async def list_images(request: Request):
    """List all images in pictures/ directory."""
    require_admin(request)
    # Return [{"name": "q001.jpg", "url": "/pictures/q001.jpg", "size": 12345}]
    ...

@router.delete("/api/admin/images/{filename}")
async def delete_image(filename: str, request: Request):
    """Delete image from pictures/ directory."""
    require_admin(request)
    # Validate filename, delete file
    ...
```

**Placeholder image**: Create `app/static/placeholder.svg` — a simple SVG with "?" icon in dark theme colors. Use in questions without images.

### 3.3 Active/inactive toggles

**New API endpoints**:

```python
@router.put("/api/admin/topics/{topic_id}/toggle")
async def toggle_topic(topic_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    # Flip is_active, return new state
    ...

@router.put("/api/admin/questions/{question_id}/toggle")
async def toggle_question(question_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    # Flip is_active, return new state
    ...
```

### 3.4 Question card layout

Replace flat table with card grid:
```html
<div class="question-cards">
    <div class="question-card">
        <div class="q-card-thumb">
            <img src="/pictures/q001.jpg" onerror="this.src='/static/placeholder.svg'">
        </div>
        <div class="q-card-body">
            <div class="q-card-text">Question text...</div>
            <div class="q-card-meta">
                <span class="diff-1">1 балл</span>
                <span class="q-card-topic">Наука</span>
            </div>
        </div>
        <div class="q-card-actions">
            <button class="toggle-btn active" onclick="toggleQuestion(id)">✓</button>
            <button class="btn btn-secondary btn-sm" onclick="editQuestion(...)">✏️</button>
            <button class="btn btn-sm" style="background:#e94560" onclick="deleteQuestion(id)">🗑️</button>
        </div>
    </div>
</div>
```

### 3.5 CSS additions in `style.css`

```css
/* Admin sidebar */
.admin-layout { display: flex; gap: 20px; min-height: calc(100vh - 100px); }
.admin-sidebar { width: 220px; flex-shrink: 0; }
.admin-sidebar .sidebar-nav { ... }
.admin-sidebar .nav-item { padding: 12px 18px; cursor: pointer; ... }
.admin-sidebar .nav-item.active { background: var(--color-primary); ... }
.admin-content { flex: 1; min-width: 0; }

/* Question cards */
.question-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 15px; }
.question-card { background: var(--bg-card); border-radius: 12px; overflow: hidden; ... }
.q-card-thumb { height: 120px; overflow: hidden; }
.q-card-thumb img { width: 100%; height: 100%; object-fit: cover; }
.q-card-body { padding: 12px; }
.q-card-meta { display: flex; gap: 8px; ... }

/* Toggle button */
.toggle-btn { width: 36px; height: 36px; border-radius: 50%; border: 2px solid ... }
.toggle-btn.active { background: var(--color-success); border-color: var(--color-success); }
.toggle-btn.inactive { background: #555; border-color: #555; }

/* Image browser modal */
.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; }
.image-item { position: relative; cursor: pointer; border-radius: 8px; overflow: hidden; }
.image-item img { width: 100%; height: 80px; object-fit: cover; }
.image-item.selected { border: 3px solid var(--color-primary); }
```

**Files modified**: `app/templates/admin.html`, `app/static/style.css`, `app/routers/admin.py`
**Files created**: `app/static/placeholder.svg`

---

## Phase 4: Game UI Improvements (F4) — Commit: "feat: circular timer SVG, deferred score update, image placeholder"

### 4.1 Circular SVG timer

Replace linear bar timer with circular SVG:

```html
<!-- Replace in room.html -->
<div class="timer-circle-wrap">
    <svg class="timer-svg" viewBox="0 0 100 100">
        <circle class="timer-bg" cx="50" cy="50" r="45" />
        <circle class="timer-progress" id="timer-circle" cx="50" cy="50" r="45" />
    </svg>
    <div class="timer-text" id="timer-text">20</div>
</div>
```

JS changes:
```javascript
function startTimer(seconds) {
    let timeLeft = seconds;
    const circle = document.getElementById('timer-circle');
    const text = document.getElementById('timer-text');
    const circumference = 2 * Math.PI * 45; // ~282.74
    circle.style.strokeDasharray = circumference;
    circle.style.strokeDashoffset = 0;
    text.textContent = Math.ceil(timeLeft);

    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        timeLeft -= 0.1;
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            timeLeft = 0;
            onTimerExpired();
        }
        const offset = circumference * (1 - timeLeft / seconds);
        circle.style.strokeDashoffset = offset;
        text.textContent = Math.ceil(timeLeft);

        // Color transition: green → yellow → red
        const ratio = timeLeft / seconds;
        if (ratio > 0.5) circle.style.stroke = '#00b894';
        else if (ratio > 0.25) circle.style.stroke = '#fdcb6e';
        else circle.style.stroke = '#e94560';
    }, 100);
}
```

### 4.2 Deferred score update

**Problem**: Scores update immediately when a team answers. Should wait until timer expires and reveal shows.

**Backend change in `app/routers/rooms.py` `submit_answer`**:

Move the score increment OUT of `submit_answer`. Instead, mark the answer record but don't update scores:

```python
# In submit_answer:
# REMOVE the score update block (lines 464-475)
# Scores will be calculated during reveal broadcast
```

**Add score calculation to reveal broadcast in `app/routers/ws.py` `broadcast_reveal_to_room`**:

After collecting answers, calculate scores:
```python
# After collecting all answers for the question:
for a in answers:
    if a.is_correct:
        # Add score to all team members
        team_members_result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.team == a.team,
                RoomMember.role == "player",
            )
        )
        q_result2 = await db.execute(select(Question).where(Question.id == q.id))
        q_obj = q_result2.scalar_one_or_none()
        for tm in team_members_result.scalars().all():
            tm.score += q_obj.difficulty if q_obj else 1
            db.add(tm)
await db.commit()
```

**Frontend change**: Remove immediate score update on answer response. Scores only update on `reveal` and `scores` WebSocket messages (which already happen).

### 4.3 Image placeholder for no-image questions

In `room.html`, replace the hidden image with placeholder:
```javascript
if (q.image_url) {
    imgEl.src = q.image_url;
    imgEl.style.display = 'block';
    imgEl.onerror = () => { imgEl.src = BASE + '/static/placeholder.svg'; };
} else {
    imgEl.src = BASE + '/static/placeholder.svg';
    imgEl.style.display = 'block';
}
```

### 4.4 CSS additions

```css
/* Circular timer */
.timer-circle-wrap { position: relative; width: 100px; height: 100px; margin: 0 auto 20px; }
.timer-svg { transform: rotate(-90deg); width: 100%; height: 100%; }
.timer-bg { fill: none; stroke: var(--bg-accent); stroke-width: 8; }
.timer-progress { fill: none; stroke: #00b894; stroke-width: 8; stroke-linecap: round; transition: stroke-dashoffset 0.1s linear; }
.timer-circle-wrap .timer-text {
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    font-size: 1.8em; font-weight: 800; color: var(--color-primary);
}
```

**Files modified**: `app/templates/room.html`, `app/static/style.css`, `app/routers/rooms.py`, `app/routers/ws.py`

---

## Phase 5: Lobby Enhancements (F5) — Commit: "feat: lobby topic selection, theme suggestions, voting sidebar"

### 5.1 Topic selection on room create

Replace the simple text input for room creation with a topic selector showing completion marks:

**Change `CreateRoomRequest`** in `rooms.py`:
```python
class CreateRoomRequest(BaseModel):
    name: str = ""
```
(Keep the same — topic is selected at game start, not room create. But show available topics in the lobby.)

**Lobby JS changes** — when showing the create room form, also show a topic preview:
```javascript
// Add after create room button
async function loadAvailableTopics() {
    const res = await fetch(BASE + '/api/game/topics');
    const topics = await res.json();
    // Show topics with question count and "completed" mark
    // "completed" = topic has >= QUESTIONS_PER_GAME active questions
}
```

### 5.2 Theme suggestion (120 chars)

**New API endpoints in a new router or add to rooms/lobby**:

```python
# app/routers/suggestions.py (new file)
router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

@router.post("")
async def suggest_topic(req: SuggestRequest, player: dict = Depends(get_current_player), db = Depends(get_db)):
    """Submit a topic suggestion. Max 120 chars."""
    if len(req.name) > 120:
        raise HTTPException(400, "Max 120 characters")
    suggestion = SuggestedTopic(
        name=req.name.strip(),
        suggested_by=player.get("nickname", "Unknown"),
        player_id=player.get("player_id"),
    )
    db.add(suggestion)
    await db.commit()
    return {"ok": True}

@router.get("")
async def list_suggestions(db = Depends(get_db)):
    """List all suggestions with vote counts, ordered by votes."""
    # JOIN with votes, compute net score
    ...

@router.post("/{suggestion_id}/vote")
async def vote_suggestion(suggestion_id: int, req: VoteRequest, player = Depends(get_current_player), db = Depends(get_db)):
    """Vote +1 or -1 on a suggestion. One vote per player."""
    ...
```

**Lobby UI**: Add suggestion input below room list:
```html
<div class="card">
    <h3>Предложить тему</h3>
    <div style="display:flex;gap:10px">
        <input type="text" id="suggest-input" placeholder="Название темы (до 120 символов)" maxlength="120">
        <button class="btn btn-primary btn-sm" onclick="suggestTopic()">Предложить</button>
    </div>
</div>
```

### 5.3 Voting sidebar

Add voting section to lobby sidebar:
```html
<div class="sidebar-section">
    <h3>💡 Предложенные темы</h3>
    <div id="suggestions-list"></div>
</div>
```

Each suggestion item:
```html
<div class="suggestion-item">
    <div class="vote-controls">
        <button class="vote-btn" onclick="vote(id, 1)">▲</button>
        <span class="vote-count">+5</span>
        <button class="vote-btn" onclick="vote(id, -1)">▼</button>
    </div>
    <div class="suggestion-text">Тема名称</div>
    <div class="suggestion-by">от Игрок1</div>
</div>
```

### 5.4 Register new router

In `app/main.py`:
```python
from app.routers import suggestions
app.include_router(suggestions.router)
```

### 5.5 CSS additions

```css
.suggestion-item { display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.vote-controls { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.vote-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.2em; padding: 2px; }
.vote-btn:hover { color: var(--color-primary); }
.vote-count { font-size: 0.9em; font-weight: 700; color: var(--color-primary); }
.suggestion-text { font-size: 0.95em; }
.suggestion-by { font-size: 0.8em; color: var(--text-secondary); }
```

**Files created**: `app/routers/suggestions.py`
**Files modified**: `app/main.py`, `app/templates/lobby.html`, `app/static/style.css`

---

## Phase 6: Room Waiting — Editable Team Name (F6) — Commit: "feat: editable team name in room waiting"

### 6.1 Backend: rename team endpoint

Currently, team names are derived from the room member's `team` field ('A' or 'B'). There's no "team name" — just "Команда A" and "Команда B". 

Looking at the spec more carefully: "editable team name" likely means the player can edit their own **nickname** while in the waiting room, not the team label.

**New endpoint in `app/routers/rooms.py`**:

```python
class UpdateNicknameRequest(BaseModel):
    nickname: str

@router.put("/{code}/nickname")
async def update_nickname(
    code: str,
    req: UpdateNicknameRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    """Allow player to edit their nickname while in waiting room."""
    # Find room, check status == 'waiting'
    # Find member by player_id/nickname
    # Validate new nickname (1-100 chars, unique in room)
    # Update and broadcast
    ...
```

### 6.2 Frontend: inline nickname editing

In `room.html` waiting section, make the player's own name editable:
```javascript
// In renderWaitingRoom, add edit button next to current user's name
// Clicking shows an inline input field
function editNickname(memberId) {
    // Show input, hide span
    // On Enter or blur, PUT /api/rooms/{code}/nickname
}
```

**Files modified**: `app/routers/rooms.py`, `app/templates/room.html`

---

## Phase 7: Mobile Fixes (F7) — Commit: "fix: mobile alignment for room name and create button"

### 7.1 CSS fixes

```css
/* In lobby create room section */
@media (max-width: 600px) {
    #create-room-section .card > div {
        flex-direction: column;
    }
    #create-room-section .card > div input {
        width: 100%;
    }
    #create-room-section .card > div button {
        width: 100%;
    }

    /* Room header alignment */
    .room-header {
        flex-direction: column;
        align-items: flex-start;
    }

    /* Top bar in room page */
    #top-bar {
        flex-direction: column;
        align-items: stretch;
    }
    .room-top-info {
        flex-wrap: wrap;
    }
    .room-scores-bar {
        justify-content: center;
    }
}
```

**Files modified**: `app/static/style.css`

---

## Phase 8: Telegram Bot (F8) — Commit: "feat: telegram bot with admin commands and notifications"

### 8.1 New dependency

Add to `requirements.txt`:
```
python-telegram-bot==21.6
```

### 8.2 New config in `app/config.py`

```python
TELEGRAM_BOT_TOKEN = os.getenv("QUIZ_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.getenv("QUIZ_TELEGRAM_ADMIN_ID", "")  # Telegram user ID
NOTIFICATION_TIME_MSK = "10:00"  # Default notification time
```

### 8.3 New file: `app/telegram_bot.py`

```python
"""Telegram bot for quiz game notifications and admin commands."""

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID

# Admin commands:
# /start — welcome message
# /stats — show game statistics (visit count, active rooms, etc.)
# /top — show top players
# /newtopics — list new topics added this week
# /votes — show top voted suggestions
# /backup — trigger backup (see F9)
# /report — weekly report (see F10)

async def start_bot():
    """Start the telegram bot as a background task."""
    if not TELEGRAM_BOT_TOKEN:
        return  # Bot disabled

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("top", cmd_top))
    # ... more handlers

    # Start polling in background
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

# Scheduled notifications:
# - New topic notification at 10:00 MSK daily
# - Weekly voting results on Mondays

async def notify_new_topic(topic_name: str):
    """Send notification when a new topic is created."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        return
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_ADMIN_ID,
        text=f"🆕 Новая тема создана: {topic_name}"
    )

async def notify_weekly_voting():
    """Send weekly voting results summary."""
    ...
```

### 8.4 Integration in `app/main.py`

```python
# In lifespan:
from app.telegram_bot import start_bot
bot_task = asyncio.create_task(start_bot())
# ...
yield
bot_task.cancel()
```

### 8.5 Admin ID check

All admin commands verify `update.effective_user.id == int(TELEGRAM_ADMIN_ID)` before executing.

**Files created**: `app/telegram_bot.py`
**Files modified**: `app/config.py`, `app/main.py`, `requirements.txt`

---

## Phase 9: Backup System (F9) — Commit: "feat: backup upload/download with bot notification"

### 9.1 Config additions in `app/config.py`

```python
BACKUP_SERVER_HOST = os.getenv("QUIZ_BACKUP_HOST", "")
BACKUP_SERVER_USER = os.getenv("QUIZ_BACKUP_USER", "")
BACKUP_SERVER_KEY = os.getenv("QUIZ_BACKUP_KEY", "")  # SSH key path
BACKUP_SERVER_PATH = os.getenv("QUIZ_BACKUP_PATH", "/backups/quiz-game/")
BACKUP_INTERVAL_DAYS = int(os.getenv("QUIZ_BACKUP_INTERVAL_DAYS", "7"))
```

### 9.2 New file: `app/backup.py`

```python
"""Backup system: upload images + CSV + DB to external server."""

import subprocess
import os
import asyncio
from datetime import datetime

BACKUP_DIR = "/tmp/quiz_backup"

async def create_backup() -> str:
    """Create a backup archive. Returns path to archive."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"quiz_backup_{timestamp}.tar.gz"
    archive_path = os.path.join(BACKUP_DIR, archive_name)

    # Tar up: pictures/, data/questions.csv, data/quiz.db
    subprocess.run([
        "tar", "-czf", archive_path,
        "-C", "/home/mi/quiz-game",
        "pictures/", "data/questions.csv", "data/quiz.db"
    ], check=True)

    return archive_path

async def upload_backup(archive_path: str):
    """Upload backup to external server via SCP."""
    if not BACKUP_SERVER_HOST:
        return False
    # Use subprocess to SCP the file
    ...

async def auto_backup_loop():
    """Background task that runs backup every N days."""
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_DAYS * 86400)
        try:
            path = await create_backup()
            await upload_backup(path)
            # Notify via bot
            from app.telegram_bot import notify_backup_complete
            await notify_backup_complete()
        except Exception:
            pass
```

### 9.3 Admin API endpoints in `app/routers/admin.py`

```python
@router.post("/api/admin/backup")
async def trigger_backup(request: Request):
    """Manually trigger backup."""
    require_admin(request)
    from app.backup import create_backup, upload_backup
    path = await create_backup()
    await upload_backup(path)
    return {"ok": True, "path": path}

@router.get("/api/admin/backup/download")
async def download_backup(request: Request):
    """Download latest backup archive."""
    require_admin(request)
    # Return FileResponse for the latest archive
    ...
```

### 9.4 Admin UI button

Add "Backup" section to admin panel (in new sidebar under a "Система" nav item or in settings):
```html
<button class="btn btn-primary" onclick="triggerBackup()">Создать бэкап</button>
<button class="btn btn-secondary" onclick="downloadBackup()">Скачать бэкап</button>
```

**Files created**: `app/backup.py`
**Files modified**: `app/config.py`, `app/main.py`, `app/routers/admin.py`, `app/templates/admin.html`

---

## Phase 10: Statistics (F10) — Commit: "feat: visit stats, game analytics, admin charts, weekly report"

### 10.1 Visit tracking middleware

Add middleware in `app/main.py` to log page visits:

```python
class VisitTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Only track page loads (HTML), not API calls
        if response.headers.get("content-type", "").startswith("text/html"):
            page = request.url.path
            # Determine page type
            if page == "/" or page == "/lobby":
                page_type = "lobby"
            elif page.startswith("/room/"):
                page_type = "room"
            elif page == "/admin":
                page_type = "admin"
            else:
                page_type = page

            # Log asynchronously (don't block response)
            asyncio.create_task(log_visit(page_type, request))
        return response
```

### 10.2 Game session tracking

Track game lifecycle events in the room endpoints:

In `start_room_game`:
```python
# Log game started
visit = VisitStat(page="game_start", player_nickname=nickname)
db.add(visit)
```

In `broadcast_game_over_to_room`:
```python
# Log game finished
visit = VisitStat(page="game_finish", player_nickname=nickname)
db.add(visit)
```

For abandoned games (inactivity checker):
```python
# Log game abandoned
visit = VisitStat(page="game_abandon")
db.add(visit)
```

### 10.3 New API endpoints

```python
# app/routers/admin.py additions
@router.get("/api/admin/stats")
async def get_stats(request: Request, db = Depends(get_db)):
    """Get comprehensive statistics."""
    require_admin(request)
    # Total visits, unique players, games started/finished/abandoned
    # Average game duration
    # Most popular topics
    # Visit trends (last 30 days)
    ...

@router.get("/api/admin/stats/visits")
async def get_visit_stats(request: Request, days: int = 30, db = Depends(get_db)):
    """Get visit statistics for chart."""
    require_admin(request)
    # Group by day, return [{date: "2026-06-15", count: 42}, ...]
    ...

@router.get("/api/admin/stats/games")
async def get_game_stats(request: Request, days: int = 30, db = Depends(get_db)):
    """Get game statistics."""
    require_admin(request)
    # Games started, finished, abandoned per day
    ...
```

### 10.4 Chart.js integration

Add Chart.js CDN in `admin.html`:
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
```

Add chart rendering in admin stats section:
```javascript
async function loadStats() {
    const res = await fetch(BASE + '/api/admin/stats/visits?days=30', {headers: headers()});
    const data = await res.json();

    new Chart(document.getElementById('visits-chart'), {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [{
                label: 'Посещения',
                data: data.map(d => d.count),
                borderColor: '#e94560',
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { labels: { color: '#eee' } } },
            scales: {
                x: { ticks: { color: '#888' } },
                y: { ticks: { color: '#888' } }
            }
        }
    });
}
```

### 10.5 Weekly report via bot

```python
# app/telegram_bot.py additions
async def send_weekly_report():
    """Generate and send weekly statistics report to admin."""
    async with async_session() as db:
        # Query stats for last 7 days
        # Format: visits, games, top players, top topics
        report = "📊 Еженедельный отчёт\n\n"
        report += f"Посещений: {visit_count}\n"
        report += f"Игр начато: {games_started}\n"
        report += f"Игр завершено: {games_finished}\n"
        report += f"Топ-3 игрока:\n"
        # ...

        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_ADMIN_ID, text=report)
```

Schedule in `start_bot`:
```python
# Weekly report on Mondays at 10:00 MSK
job_queue = app.job_queue
job_queue.run_daily(send_weekly_report, time=datetime.time(hour=7, minute=0), days=(0,))  # 7:00 UTC = 10:00 MSK
```

**Files modified**: `app/main.py`, `app/routers/admin.py`, `app/templates/admin.html`, `app/static/style.css`, `app/telegram_bot.py`

---

## Phase 11: Tests (F11) — ✅ DONE — Commit: "test: add tests for all new features"

### 11.1 Test files to create/modify

**`tests/test_suggestions.py`** (new):
```python
# Test suggest topic
# Test list suggestions
# Test vote +1
# Test vote -1
# Test vote change (same player, different direction)
# Test duplicate vote rejection
# Test max length validation (120 chars)
# ~8-10 tests
```

**`tests/test_admin_extended.py`** (new):
```python
# Test toggle topic active/inactive
# Test toggle question active/inactive
# Test image upload (mock file)
# Test list images
# Test delete image
# Test get stats
# Test get visit stats
# Test get game stats
# ~10-12 tests
```

**`tests/test_backup.py`** (new) ✅:
```python
# Test create backup (mock filesystem) ✅
# Test backup triggers correctly ✅
# Test admin-only access ✅
# 5 tests created and passing
```

**`tests/test_telegram.py`** (new) ✅:
```python
# Test admin ID check ✅
# Test command handlers (mock bot) ✅
# Test notification functions ✅
# 10 tests created and passing
```

**`tests/test_rooms.py`** (modify):
```python
# Add: test_update_nickname_in_waiting_room
# Add: test_update_nickname_in_active_room (should fail)
# Add: test_update_nickname_duplicate_in_room
# Add: test_deferred_score_update (scores don't change on answer, change on reveal)
# Add: test_inactive_questions_excluded_from_game
# ~3-5 new tests
```

**`tests/test_admin.py`** (modify):
```python
# Add: test_toggle_topic_active
# Add: test_toggle_question_active
# ~2 new tests
```

**`tests/test_game.py`** (modify):
```python
# Add: test_inactive_topics_excluded_from_list
# Add: test_inactive_questions_not_selected
# ~2 new tests
```

### 11.2 Total new tests: ~30-42 tests ✅ (150 total passing)

### 11.3 Test fixtures updates

In `tests/conftest.py`, add:
```python
@pytest_asyncio.fixture
async def player_token(client):
    """Register a player and return token."""
    res = await client.post("/api/auth/player/register", json={
        "nickname": "TestPlayer",
        "email": "test@test.com",
        "password": "pass1234",
    })
    return res.json()["token"]
```

---

## Phase 12: Git Commits (F12)

Each phase maps to one commit:

| # | Commit message | Files touched |
|---|---|---|
| 1 | `fix: CSS path, port mismatch, nginx static locations` | `base.html`, `nginx/quiz-game.conf`, `start.sh`, `run.py`, `config.py` |
| 2 | `feat: is_active flags, suggested_topics, topic_votes, visit_stats tables` | `models.py`, `database.py`, `game.py`, `rooms.py` |
| 3 | `feat: admin sidebar nav, image upload, question cards, active toggles` | `admin.html`, `style.css`, `admin.py`, `placeholder.svg` |
| 4 | `feat: circular SVG timer, deferred scores, image placeholder` | `room.html`, `style.css`, `rooms.py`, `ws.py` |
| 5 | `feat: lobby topic selection, theme suggestions, voting sidebar` | `suggestions.py` (new), `main.py`, `lobby.html`, `style.css` |
| 6 | `feat: editable nickname in room waiting` | `rooms.py`, `room.html` |
| 7 | `fix: mobile alignment for room name and create button` | `style.css` |
| 8 | `feat: telegram bot with admin commands and notifications` | `telegram_bot.py` (new), `config.py`, `main.py`, `requirements.txt` |
| 9 | `feat: backup upload/download with bot notification` | `backup.py` (new), `config.py`, `main.py`, `admin.py`, `admin.html` |
| 10 | `feat: visit stats, game analytics, admin charts, weekly report` | `main.py`, `admin.py`, `admin.html`, `style.css`, `telegram_bot.py` |
| 11 | `test: add tests for all new features` | `test_suggestions.py`, `test_admin_extended.py`, `test_backup.py`, `test_telegram.py`, `test_rooms.py`, `test_admin.py`, `test_game.py`, `conftest.py` |

---

## Dependency Summary

### New Python packages
```
python-telegram-bot==21.6   # F8
```

### New config env vars
```
QUIZ_PORT                    # F1 (default: 8080)
QUIZ_TELEGRAM_BOT_TOKEN      # F8
QUIZ_TELEGRAM_ADMIN_ID       # F8
QUIZ_BACKUP_HOST             # F9
QUIZ_BACKUP_USER             # F9
QUIZ_BACKUP_KEY              # F9
QUIZ_BACKUP_PATH             # F9
QUIZ_BACKUP_INTERVAL_DAYS    # F9
```

### New files
| File | Phase |
|---|---|
| `app/static/placeholder.svg` | F3 |
| `app/routers/suggestions.py` | F5 |
| `app/telegram_bot.py` | F8 |
| `app/backup.py` | F9 |
| `tests/test_suggestions.py` | F11 |
| `tests/test_admin_extended.py` | F11 |
| `tests/test_backup.py` | F11 |
| `tests/test_telegram.py` | F11 |

### New API endpoints summary

| Method | Path | Phase |
|---|---|---|
| POST | `/api/admin/upload-image` | F3 |
| GET | `/api/admin/images` | F3 |
| DELETE | `/api/admin/images/{filename}` | F3 |
| PUT | `/api/admin/topics/{id}/toggle` | F3 |
| PUT | `/api/admin/questions/{id}/toggle` | F3 |
| POST | `/api/suggestions` | F5 |
| GET | `/api/suggestions` | F5 |
| POST | `/api/suggestions/{id}/vote` | F5 |
| PUT | `/api/rooms/{code}/nickname` | F6 |
| POST | `/api/admin/backup` | F9 |
| GET | `/api/admin/backup/download` | F9 |
| GET | `/api/admin/stats` | F10 |
| GET | `/api/admin/stats/visits` | F10 |
| GET | `/api/admin/stats/games` | F10 |

### DB schema changes summary

| Table | Column/Change | Type |
|---|---|---|
| topics | `is_active` added | `Boolean, default=True` |
| questions | `is_active` added | `Boolean, default=True` |
| suggested_topics | **new table** | id, name(120), suggested_by, player_id, created_at |
| topic_votes | **new table** | id, suggested_topic_id(FK), player_nickname, vote(+1/-1), voted_at |
| visit_stats | **new table** | id, page, player_nickname, visited_at, session_duration |

---

## Risk Assessment

1. **Deferred score update (F4)** — changes core game logic. Existing tests that check immediate score changes will need updating. Must verify reveal→score flow carefully.
2. **Telegram bot (F8)** — adds external dependency. Must gracefully handle missing token (bot disabled). Background task lifecycle must not block app startup.
3. **Image upload (F3)** — needs `python-multipart` (already in requirements). Must validate file types and sizes. Security: sanitize filenames to prevent path traversal.
4. **Backup (F9)** — relies on external server SSH access. Must handle connection failures gracefully.
5. **Chart.js (F10)** — external CDN dependency. Consider fallback or self-hosting.
6. **Score timing race** — deferred scores mean if the server crashes between answer and reveal, scores are lost. Acceptable for a quiz game.
