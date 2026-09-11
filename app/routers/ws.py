import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth import verify_token
from app.config import ANSWER_GRACE_MULTIPLIER, ANSWER_TIME_SECONDS, READING_TIME_SECONDS
from app.database import async_session
from app.models import Game, Question, Room, RoomAnswer, RoomMember, Team, TeamAnswer

router = APIRouter()

# Old global game WebSocket
connected_clients: list[WebSocket] = []

# Room-scoped WebSocket connections
room_connections: dict[str, list[dict]] = {}

# In-memory round state: tracks confirmations per room per question
# Key: room_code, Value: {question_id, confirmed: {member_id: selected_option}, dropped: set, grace_task, round_lock}


class RoundState:
    def __init__(self, question_id: int):
        self.question_id = question_id
        self.confirmed: dict[int, str | None] = {}  # member_id -> selected_option (or None)
        self.dropped: set[str] = set()  # nicknames of dropped players
        self.grace_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.finished = False


_round_states: dict[str, RoundState] = {}


@router.websocket("/ws/game")
async def websocket_game(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        if ws in connected_clients:
            connected_clients.remove(ws)
    except Exception:
        if ws in connected_clients:
            connected_clients.remove(ws)


@router.websocket("/ws/room/{room_code}")
async def websocket_room(ws: WebSocket, room_code: str):
    room_code = room_code.upper()
    await ws.accept()

    client_info = {"ws": ws, "role": "observer", "team": None, "nickname": "Unknown"}

    # Wait for auth message
    try:
        data = await ws.receive_text()
        msg = json.loads(data)
        if msg.get("type") == "auth":
            token = msg.get("token", "")
            payload = verify_token(token)
            if payload:
                client_info["nickname"] = payload.get("nickname", "Unknown")
                # Role and team will be set based on room membership
                async with async_session() as db:
                    result = await db.execute(select(Room).where(Room.code == room_code))
                    room = result.scalar_one_or_none()
                    if room:
                        member_result = await db.execute(
                            select(RoomMember).where(
                                RoomMember.room_id == room.id,
                                RoomMember.nickname == client_info["nickname"],
                            )
                        )
                        member = member_result.scalar_one_or_none()
                        if member:
                            client_info["role"] = member.role
                            client_info["team"] = member.team
    except Exception:
        pass

    if room_code not in room_connections:
        room_connections[room_code] = []
    room_connections[room_code].append(client_info)

    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
                continue
            try:
                msg = json.loads(data)
                if msg.get("type") == "timer_exp":
                    await handle_timer_exp(ws, room_code, msg.get("data", {}), client_info)
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        if room_code in room_connections and client_info in room_connections[room_code]:
            room_connections[room_code].remove(client_info)
    except Exception:
        if room_code in room_connections and client_info in room_connections[room_code]:
            room_connections[room_code].remove(client_info)


async def broadcast(message: dict):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


async def broadcast_to_room(room_code: str, message: dict):
    if room_code not in room_connections:
        return
    dead = []
    for client in room_connections[room_code]:
        try:
            await client["ws"].send_json(message)
        except Exception:
            dead.append(client)
    for client in dead:
        room_connections[room_code].remove(client)


async def broadcast_question(game_id: int):
    async with async_session() as db:
        result = await db.execute(select(Game).where(Game.id == game_id))
        game = result.scalar_one_or_none()
        if not game:
            return

        question_ids = game.get_questions_order()
        if game.current_question_index < 0 or game.current_question_index >= len(question_ids):
            return

        qid = question_ids[game.current_question_index]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if not q:
            return

        await broadcast(
            {
                "type": "question",
                "data": {
                    "id": q.id,
                    "text": q.text,
                    "image_url": q.image_url,
                    "option_a": q.option_a,
                    "option_b": q.option_b,
                    "option_c": q.option_c,
                    "option_d": q.option_d,
                    "difficulty": q.difficulty,
                    "index": game.current_question_index + 1,
                    "total": len(question_ids),
                    "time_left": ANSWER_TIME_SECONDS,
                },
            }
        )


async def broadcast_question_to_room(room_code: str):
    room_obj = None
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room:
            return

        question_ids = room.get_questions_order()
        if room.current_question_index < 0 or room.current_question_index >= len(question_ids):
            return

        qid = question_ids[room.current_question_index]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if not q:
            return

        # Detach room data we need after session close
        room_obj = {
            "id": room.id,
            "code": room.code,
            "current_question_index": room.current_question_index,
            "questions_order": room.questions_order,
            "round_phase": room.round_phase,
        }

        await broadcast_to_room(
            room_code,
            {
                "type": "question",
                "data": {
                    "id": q.id,
                    "text": q.text,
                    "image_url": q.image_url,
                    "option_a": q.option_a,
                    "option_b": q.option_b,
                    "option_c": q.option_c,
                    "option_d": q.option_d,
                    "correct_option": q.correct_option,
                    "explanation": q.explanation,
                    "difficulty": q.difficulty,
                    "index": room.current_question_index + 1,
                    "total": len(question_ids),
                    "time": ANSWER_TIME_SECONDS,
                },
            },
        )

    # Initialize round state
    if room_obj:
        await start_round(room_code, room_obj)


async def broadcast_reveal(game_id: int):
    async with async_session() as db:
        result = await db.execute(select(Game).where(Game.id == game_id))
        game = result.scalar_one_or_none()
        if not game:
            return

        question_ids = game.get_questions_order()
        if game.current_question_index < 0:
            return

        qid = question_ids[game.current_question_index]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if not q:
            return

        ans_result = await db.execute(
            select(TeamAnswer).where(
                TeamAnswer.game_id == game_id,
                TeamAnswer.question_id == q.id,
            )
        )
        answers = ans_result.scalars().all()

        teams_result = await db.execute(select(Team))
        teams = {t.id: t for t in teams_result.scalars().all()}

        answer_details = []
        for a in answers:
            t = teams.get(a.team_id)
            answer_details.append(
                {
                    "team_id": a.team_id,
                    "team_name": t.name if t else "Unknown",
                    "selected_option": a.selected_option,
                    "is_correct": a.is_correct,
                }
            )

        await broadcast(
            {
                "type": "reveal",
                "data": {
                    "correct_option": q.correct_option,
                    "explanation": q.explanation,
                    "answers": answer_details,
                    "teams": [{"id": t.id, "name": t.name, "score": t.score} for t in teams.values()],
                },
            }
        )


async def broadcast_reveal_to_room(room_code: str):
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room:
            return

        question_ids = room.get_questions_order()
        if room.current_question_index < 0:
            return

        qid = question_ids[room.current_question_index]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if not q:
            return

        ans_result = await db.execute(
            select(RoomAnswer).where(
                RoomAnswer.room_id == room.id,
                RoomAnswer.question_id == q.id,
            )
        )
        answers = ans_result.scalars().all()

        # Calculate and persist scores for correct answers (deferred scoring)
        correct_teams = set()
        for a in answers:
            if a.is_correct:
                correct_teams.add(a.team)

        for team in correct_teams:
            team_members_result = await db.execute(
                select(RoomMember).where(
                    RoomMember.room_id == room.id,
                    RoomMember.team == team,
                    RoomMember.role == "player",
                )
            )
            for tm in team_members_result.scalars().all():
                tm.score += q.difficulty
                db.add(tm)

        if correct_teams:
            await db.commit()

        answer_details = []
        for a in answers:
            m_result = await db.execute(select(RoomMember).where(RoomMember.id == a.room_member_id))
            m = m_result.scalar_one_or_none()
            answer_details.append(
                {
                    "team": a.team,
                    "member_nickname": m.nickname if m else "Unknown",
                    "selected_option": a.selected_option,
                    "is_correct": a.is_correct,
                }
            )

        members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
        members = members_result.scalars().all()
        team_a_score = sum(m.score for m in members if m.team == "A" and m.role == "player")
        team_b_score = sum(m.score for m in members if m.team == "B" and m.role == "player")

        await broadcast_to_room(
            room_code,
            {
                "type": "reveal",
                "data": {
                    "correct_option": q.correct_option,
                    "explanation": q.explanation,
                    "answers": answer_details,
                    "team_a_score": team_a_score,
                    "team_b_score": team_b_score,
                },
            },
        )


async def handle_timer_exp(ws, room_code: str, data: dict, client_info: dict):
    """Handle timer_exp WS message: player confirms timer expired with their selected option."""
    question_id = data.get("question_id")
    option = data.get("option")  # "A"/"B"/"C"/"D" or null

    async with async_session() as db:
        # Validate room
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room or room.status != "active":
            return

        room_id = room.id

        # Find member
        nickname = client_info.get("nickname", "Unknown")
        member_result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.nickname == nickname,
                RoomMember.role == "player",
            )
        )
        member = member_result.scalar_one_or_none()
        if not member:
            return

        member_id = member.id
        member_team = member.team

    # Get or check round state
    rs = _round_states.get(room_code)
    if not rs or rs.question_id != question_id or rs.finished:
        return

    async with rs.lock:
        if member_id in rs.confirmed:
            return  # already confirmed

        # Record the answer
        rs.confirmed[member_id] = option.upper() if option else None

        # Persist answer to DB
        if option:
            async with async_session() as db:
                q_result = await db.execute(select(Question).where(Question.id == question_id))
                q = q_result.scalar_one_or_none()
                is_correct = option.upper() == q.correct_option if q else False

                answer = RoomAnswer(
                    room_id=room_id,
                    room_member_id=member_id,
                    team=member_team,
                    question_id=question_id,
                    selected_option=option.upper(),
                    is_correct=is_correct,
                )
                db.add(answer)
                await db.commit()

        # Broadcast player_ready to all
        player_count = await _get_player_count(room_code, room_id)
        await broadcast_to_room(
            room_code,
            {
                "type": "player_ready",
                "data": {
                    "nickname": nickname,
                    "total_ready": len(rs.confirmed),
                    "total_players": player_count,
                },
            },
        )

        # Check if all players confirmed
        if len(rs.confirmed) >= player_count:
            # Cancel grace timeout
            if rs.grace_task:
                rs.grace_task.cancel()
                rs.grace_task = None

    # Finish round outside the lock to avoid deadlock
    if len(rs.confirmed) >= await _get_player_count(room_code, room_id):
        async with async_session() as db:
            result = await db.execute(select(Room).where(Room.code == room_code))
            room = result.scalar_one_or_none()
            if room:
                await finish_round(room_code, room)


async def _get_player_count(room_code: str, room_id: int) -> int:
    async with async_session() as db:
        result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.role == "player",
            )
        )
        return len(result.scalars().all())


async def start_round(room_code: str, room):
    """Initialize round state and start grace timeout.

    `room` can be an ORM Room object or a dict with keys:
    id, code, current_question_index, questions_order, round_phase.
    """
    # Support both ORM and dict
    qi = (
        room.current_question_index
        if hasattr(room, "current_question_index")
        else room.get("current_question_index", -1)
    )
    qo = (
        room.get_questions_order()
        if hasattr(room, "get_questions_order")
        else json.loads(room.get("questions_order", "[]"))
    )

    question_ids = qo
    if qi < 0 or qi >= len(question_ids):
        return

    qid = question_ids[qi]

    # Clean up old round state
    old = _round_states.get(room_code)
    if old and old.grace_task:
        old.grace_task.cancel()

    rs = RoundState(qid)
    _round_states[room_code] = rs

    # Update room phase
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        r = result.scalar_one_or_none()
        if r:
            r.round_phase = "answering"
            r.round_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()

    # Start grace timeout
    grace_seconds = ANSWER_TIME_SECONDS * ANSWER_GRACE_MULTIPLIER
    rs.grace_task = asyncio.create_task(_grace_timeout(room_code, grace_seconds))


async def _grace_timeout(room_code: str, delay: float):
    """After grace period, finish round even if not all players confirmed."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return

    rs = _round_states.get(room_code)
    if not rs or rs.finished:
        return

    # Find players who didn't confirm → dropped
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room:
            return

        members_result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.role == "player",
            )
        )
        all_members = [(m.id, m.nickname) for m in members_result.scalars().all()]

    async with rs.lock:
        for mid, mnickname in all_members:
            if mid not in rs.confirmed:
                rs.dropped.add(mnickname)

        # Cancel grace task ref
        rs.grace_task = None

    # Notify about dropped players
    for nickname in rs.dropped:
        await broadcast_to_room(room_code, {"type": "player_dropped", "data": {"nickname": nickname}})

    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if room:
            await finish_round(room_code, room)


async def finish_round(room_code: str, room):
    """Calculate scores, send answer_result, schedule reading phase."""
    rs = _round_states.get(room_code)
    if not rs or rs.finished:
        return

    async with rs.lock:
        rs.finished = True

    question_ids = room.get_questions_order()
    qid = question_ids[room.current_question_index] if 0 <= room.current_question_index < len(question_ids) else None

    if not qid:
        return

    async with async_session() as db:
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if not q:
            return

        # Fetch answers
        ans_result = await db.execute(
            select(RoomAnswer).where(RoomAnswer.room_id == room.id, RoomAnswer.question_id == qid)
        )
        answers = ans_result.scalars().all()

        # Deferred scoring
        correct_teams = set()
        for a in answers:
            if a.is_correct:
                correct_teams.add(a.team)

        for team in correct_teams:
            team_members_result = await db.execute(
                select(RoomMember).where(
                    RoomMember.room_id == room.id,
                    RoomMember.team == team,
                    RoomMember.role == "player",
                )
            )
            for tm in team_members_result.scalars().all():
                tm.score += q.difficulty
                db.add(tm)

        if correct_teams:
            await db.commit()

        # Build answer details
        answer_details = []
        for a in answers:
            m_result = await db.execute(select(RoomMember).where(RoomMember.id == a.room_member_id))
            m = m_result.scalar_one_or_none()
            answer_details.append(
                {
                    "team": a.team,
                    "member_nickname": m.nickname if m else "Unknown",
                    "selected_option": a.selected_option,
                    "is_correct": a.is_correct,
                }
            )

        # Team scores
        members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
        members = members_result.scalars().all()
        team_a_score = sum(m.score for m in members if m.team == "A" and m.role == "player")
        team_b_score = sum(m.score for m in members if m.team == "B" and m.role == "player")

        # Update room phase
        result = await db.execute(select(Room).where(Room.code == room_code))
        r = result.scalar_one_or_none()
        if r:
            r.round_phase = "results"
            await db.commit()

    # Broadcast answer_result
    await broadcast_to_room(
        room_code,
        {
            "type": "answer_result",
            "data": {
                "correct_option": q.correct_option,
                "explanation": q.explanation,
                "answers": answer_details,
                "team_a_score": team_a_score,
                "team_b_score": team_b_score,
                "dropped": list(rs.dropped),
            },
        },
    )

    # Schedule reading phase
    asyncio.create_task(_reading_phase(room_code, READING_TIME_SECONDS))


async def _reading_phase(room_code: str, delay: float):
    """After reading time, advance to next question."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return

    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room or room.status != "active":
            return

        question_ids = room.get_questions_order()
        next_idx = room.current_question_index + 1

        if next_idx >= len(question_ids):
            # Game over
            room.status = "finished"
            room.round_phase = None
            room.last_activity_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
            await broadcast_game_over_to_room(room_code)
            return

        # Advance
        room.current_question_index = next_idx
        room.question_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        room.last_activity_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()

    # Clean up old round state
    old = _round_states.pop(room_code, None)
    if old and old.grace_task:
        old.grace_task.cancel()

    # Broadcast next question
    await broadcast_question_to_room(room_code)

    # Start new round state
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if room:
            await start_round(room_code, room)


async def broadcast_scores():
    async with async_session() as db:
        teams_result = await db.execute(select(Team))
        teams = teams_result.scalars().all()
        await broadcast(
            {
                "type": "scores",
                "data": {
                    "teams": [{"id": t.id, "name": t.name, "score": t.score} for t in teams],
                },
            }
        )


async def broadcast_scores_to_room(room_code: str):
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room:
            return

        members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
        members = members_result.scalars().all()

        team_a_score = sum(m.score for m in members if m.team == "A" and m.role == "player")
        team_b_score = sum(m.score for m in members if m.team == "B" and m.role == "player")

        await broadcast_to_room(
            room_code,
            {
                "type": "scores",
                "data": {
                    "team_a_score": team_a_score,
                    "team_b_score": team_b_score,
                    "team_a_members": [
                        {"nickname": m.nickname, "score": m.score}
                        for m in members
                        if m.team == "A" and m.role == "player"
                    ],
                    "team_b_members": [
                        {"nickname": m.nickname, "score": m.score}
                        for m in members
                        if m.team == "B" and m.role == "player"
                    ],
                },
            },
        )


async def broadcast_game_over():
    async with async_session() as db:
        teams_result = await db.execute(select(Team).order_by(Team.score.desc()))
        teams = teams_result.scalars().all()
        await broadcast(
            {
                "type": "game_over",
                "data": {
                    "teams": [
                        {"id": t.id, "name": t.name, "avatar_url": t.avatar_url, "score": t.score} for t in teams
                    ],
                },
            }
        )


async def broadcast_game_over_to_room(room_code: str):
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room:
            return

        members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
        members = members_result.scalars().all()

        team_a_score = sum(m.score for m in members if m.team == "A" and m.role == "player")
        team_b_score = sum(m.score for m in members if m.team == "B" and m.role == "player")

        await broadcast_to_room(
            room_code,
            {
                "type": "game_over",
                "data": {
                    "team_a_score": team_a_score,
                    "team_b_score": team_b_score,
                    "team_a_members": [
                        {"nickname": m.nickname, "score": m.score}
                        for m in members
                        if m.team == "A" and m.role == "player"
                    ],
                    "team_b_members": [
                        {"nickname": m.nickname, "score": m.score}
                        for m in members
                        if m.team == "B" and m.role == "player"
                    ],
                },
            },
        )


async def broadcast_room_update(room_code: str):
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if not room:
            return

        members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
        members = members_result.scalars().all()

        await broadcast_to_room(
            room_code,
            {
                "type": "room_update",
                "data": {
                    "team_a": [{"nickname": m.nickname} for m in members if m.team == "A" and m.role == "player"],
                    "team_b": [{"nickname": m.nickname} for m in members if m.team == "B" and m.role == "player"],
                    "observers_count": len([m for m in members if m.role == "observer"]),
                },
            },
        )


async def broadcast_room_closed(room_code: str):
    await broadcast_to_room(
        room_code,
        {
            "type": "room_closed",
            "data": {"reason": "inactivity"},
        },
    )
