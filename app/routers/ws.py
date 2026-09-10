import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth import verify_token
from app.config import ANSWER_TIME_SECONDS
from app.database import async_session
from app.models import Game, Question, Room, RoomAnswer, RoomMember, Team, TeamAnswer

router = APIRouter()

# Old global game WebSocket
connected_clients: list[WebSocket] = []

# Room-scoped WebSocket connections
room_connections: dict[str, list[dict]] = {}


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
                    "difficulty": q.difficulty,
                    "index": room.current_question_index + 1,
                    "total": len(question_ids),
                    "time_left": ANSWER_TIME_SECONDS,
                },
            },
        )


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
