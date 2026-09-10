import asyncio
import random
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_player
from app.config import ANSWER_TIME_SECONDS, MAX_PLAYERS_PER_TEAM, QUESTIONS_PER_GAME, ROOM_CODE_LENGTH
from app.database import get_db
from app.models import Question, Room, RoomAnswer, RoomMember, Topic

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

# Lock to prevent race condition when multiple clients call /next simultaneously
_next_question_lock = asyncio.Lock()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_room_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=ROOM_CODE_LENGTH))


class CreateRoomRequest(BaseModel):
    name: str = ""
    topic_id: int = 0
    is_private: bool = False


class JoinRequest(BaseModel):
    team: str  # 'A' or 'B'
    role: str = "player"  # 'player' or 'observer'


class StartRequest(BaseModel):
    topic_id: int


class AnswerRequest(BaseModel):
    question_id: int
    option: str


class NicknameRequest(BaseModel):
    nickname: str


@router.post("")
async def create_room(
    req: CreateRoomRequest = CreateRoomRequest(),
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    code = generate_room_code()
    # Ensure unique code
    for _ in range(10):
        existing = await db.execute(select(Room).where(Room.code == code))
        if not existing.scalar_one_or_none():
            break
        code = generate_room_code()

    # Topic selection is required
    if not req.topic_id:
        raise HTTPException(status_code=400, detail="Выберите тему для игры")

    topic_result = await db.execute(select(Topic).where(Topic.id == req.topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Тема не найдена")

    # Auto-generate name if not provided
    name = req.name.strip()
    if not name:
        count_result = await db.execute(select(Room))
        room_count = len(count_result.scalars().all())
        name = f"Комната {room_count + 1}"

    room = Room(
        code=code,
        name=name,
        status="waiting",
        topic_id=req.topic_id,
        is_private=req.is_private,
        last_activity_at=utcnow(),
    )
    db.add(room)
    await db.flush()

    member = RoomMember(
        room_id=room.id,
        nickname=player["nickname"],
        player_id=player.get("player_id"),
        team="A",
        role="player",
        score=0,
    )
    db.add(member)
    await db.commit()
    await db.refresh(room)

    return {"id": room.id, "code": room.code, "name": room.name, "status": room.status, "is_private": room.is_private}


@router.get("")
async def list_rooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Room)
        .where(Room.status.in_(["waiting", "active"]), Room.is_private == False)  # noqa: E712
        .order_by(Room.created_at.desc())
    )
    rooms = result.scalars().all()

    rooms_data = []
    for room in rooms:
        members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
        members = members_result.scalars().all()
        players_a = [m for m in members if m.role == "player" and m.team == "A"]
        players_b = [m for m in members if m.role == "player" and m.team == "B"]
        observers = [m for m in members if m.role == "observer"]

        topic_name = None
        if room.topic_id:
            t_result = await db.execute(select(Topic).where(Topic.id == room.topic_id))
            topic = t_result.scalar_one_or_none()
            if topic:
                topic_name = topic.name

        rooms_data.append(
            {
                "id": room.id,
                "code": room.code,
                "name": room.name or f"Комната {room.id}",
                "status": room.status,
                "topic": topic_name,
                "team_a": [{"nickname": m.nickname, "score": m.score} for m in players_a],
                "team_b": [{"nickname": m.nickname, "score": m.score} for m in players_b],
                "observers_count": len(observers),
            }
        )

    return rooms_data


@router.get("/{code}")
async def get_room(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
    members = members_result.scalars().all()

    topic_name = None
    if room.topic_id:
        t_result = await db.execute(select(Topic).where(Topic.id == room.topic_id))
        topic = t_result.scalar_one_or_none()
        if topic:
            topic_name = topic.name

    return {
        "id": room.id,
        "code": room.code,
        "name": room.name or f"Комната {room.id}",
        "status": room.status,
        "is_private": room.is_private,
        "topic": topic_name,
        "topic_id": room.topic_id,
        "current_question_index": room.current_question_index,
        "team_a": [
            {"id": m.id, "nickname": m.nickname, "score": m.score}
            for m in members
            if m.role == "player" and m.team == "A"
        ],
        "team_b": [
            {"id": m.id, "nickname": m.nickname, "score": m.score}
            for m in members
            if m.role == "player" and m.team == "B"
        ],
        "observers": [{"id": m.id, "nickname": m.nickname} for m in members if m.role == "observer"],
    }


@router.post("/{code}/join")
async def join_room(
    code: str,
    req: JoinRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status == "finished":
        raise HTTPException(status_code=400, detail="Room is closed")

    nickname = player.get("nickname", "Unknown")
    player_id = player.get("player_id")

    # Check if already in this room
    existing = await db.execute(
        select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.nickname == nickname,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in this room")

    team = req.team.upper()
    if team not in ("A", "B"):
        raise HTTPException(status_code=400, detail="Team must be A or B")

    role = req.role
    if role not in ("player", "observer"):
        raise HTTPException(status_code=400, detail="Role must be player or observer")

    # Check team capacity for players
    if role == "player":
        team_members = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.team == team,
                RoomMember.role == "player",
            )
        )
        if len(team_members.scalars().all()) >= MAX_PLAYERS_PER_TEAM:
            raise HTTPException(status_code=400, detail=f"Team {team} is full ({MAX_PLAYERS_PER_TEAM} max)")

    member = RoomMember(
        room_id=room.id,
        player_id=player_id,
        nickname=nickname,
        team=team,
        role=role,
    )
    db.add(member)
    room.last_activity_at = utcnow()
    db.add(room)
    await db.commit()

    # Broadcast room update
    from app.routers.ws import broadcast_room_update

    await broadcast_room_update(room.code)

    return {"ok": True, "room_code": room.code, "team": team, "role": role}


@router.post("/{code}/leave")
async def leave_room(
    code: str,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    nickname = player.get("nickname", "Unknown")
    member_result = await db.execute(
        select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.nickname == nickname,
        )
    )
    member = member_result.scalar_one_or_none()
    if member:
        await db.delete(member)
        room.last_activity_at = utcnow()
        db.add(room)
        await db.commit()

        from app.routers.ws import broadcast_room_update

        await broadcast_room_update(room.code)

    return {"ok": True}


@router.put("/{code}/nickname")
async def update_nickname(
    code: str,
    req: NicknameRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Can only change nickname in waiting room")

    nickname = player.get("nickname", "Unknown")
    new_nickname = req.nickname.strip()
    if not new_nickname or len(new_nickname) > 100:
        raise HTTPException(status_code=400, detail="Никнейм от 1 до 100 символов")

    member_result = await db.execute(
        select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.nickname == nickname,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="You are not in this room")

    member.nickname = new_nickname
    db.add(member)
    room.last_activity_at = utcnow()
    db.add(room)
    await db.commit()

    from app.routers.ws import broadcast_room_update

    await broadcast_room_update(room.code)

    return {"ok": True, "nickname": new_nickname}


@router.post("/{code}/start")
async def start_room_game(
    code: str,
    req: StartRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Room is not in waiting state")

    # Check at least 1 player per team
    for team in ("A", "B"):
        team_result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.team == team,
                RoomMember.role == "player",
            )
        )
        if len(team_result.scalars().all()) < 1:
            raise HTTPException(status_code=400, detail=f"Need at least 1 player in Team {team}")

    # Verify topic
    topic_result = await db.execute(select(Topic).where(Topic.id == req.topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    q_result = await db.execute(
        select(Question).where(Question.topic_id == req.topic_id, Question.is_active == True)  # noqa: E712
    )
    all_questions = q_result.scalars().all()
    if len(all_questions) < QUESTIONS_PER_GAME:
        raise HTTPException(
            status_code=400,
            detail=f"Topic has {len(all_questions)} questions, need at least {QUESTIONS_PER_GAME}",
        )

    selected = random.sample(list(all_questions), QUESTIONS_PER_GAME)
    question_ids = [q.id for q in selected]

    room.status = "active"
    room.topic_id = req.topic_id
    room.current_question_index = -1
    room.set_questions_order(question_ids)
    room.started_at = utcnow()
    room.last_activity_at = utcnow()

    # Reset member scores
    members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
    for m in members_result.scalars().all():
        m.score = 0
        db.add(m)

    await db.commit()

    return {"ok": True, "status": "active", "topic": topic.name, "questions_count": len(question_ids)}


@router.post("/{code}/next")
async def next_question(
    code: str,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    async with _next_question_lock:
        result = await db.execute(select(Room).where(Room.code == code.upper()))
        room = result.scalar_one_or_none()
        if not room or room.status != "active":
            raise HTTPException(status_code=400, detail="No active game in this room")

        question_ids = room.get_questions_order()

        # Prevent advancing if current question time hasn't expired yet
        if room.current_question_index >= 0 and room.question_started_at:
            elapsed = (utcnow() - room.question_started_at).total_seconds()
            if elapsed < ANSWER_TIME_SECONDS:
                raise HTTPException(status_code=400, detail="Question time has not expired yet")

        # Broadcast reveal for the current question before advancing
        if room.current_question_index >= 0:
            from app.routers.ws import broadcast_reveal_to_room

            await broadcast_reveal_to_room(room.code)

        next_idx = room.current_question_index + 1

        if next_idx >= len(question_ids):
            room.status = "finished"
            room.last_activity_at = utcnow()
            await db.commit()
            from app.routers.ws import broadcast_game_over_to_room

            await broadcast_game_over_to_room(room.code)
            return {"status": "finished"}

        room.current_question_index = next_idx
        room.question_started_at = utcnow()
        room.last_activity_at = utcnow()
        await db.commit()

        from app.routers.ws import broadcast_question_to_room

        await broadcast_question_to_room(room.code)

        qid = question_ids[next_idx]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()

        return {
            "status": "active",
            "question": {
                "id": q.id,
                "text": q.text,
                "image_url": q.image_url,
                "option_a": q.option_a,
                "option_b": q.option_b,
                "option_c": q.option_c,
                "option_d": q.option_d,
                "difficulty": q.difficulty,
                "index": next_idx + 1,
                "total": QUESTIONS_PER_GAME,
            }
            if q
            else None,
        }


@router.post("/{code}/answer")
async def submit_answer(
    code: str,
    req: AnswerRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    if req.option.upper() not in ("A", "B", "C", "D"):
        raise HTTPException(status_code=400, detail="Option must be A, B, C, or D")

    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room or room.status != "active":
        raise HTTPException(status_code=400, detail="No active game in this room")

    if room.question_started_at:
        elapsed = (utcnow() - room.question_started_at).total_seconds()
        if elapsed >= ANSWER_TIME_SECONDS:
            raise HTTPException(status_code=400, detail="Time is up")

    question_ids = room.get_questions_order()
    if room.current_question_index < 0 or room.current_question_index >= len(question_ids):
        raise HTTPException(status_code=400, detail="No current question")

    current_qid = question_ids[room.current_question_index]

    # Validate that the submitted question_id matches the current question
    if req.question_id != current_qid:
        raise HTTPException(status_code=400, detail="This question is no longer active")

    # Find the member
    nickname = player.get("nickname", "Unknown")
    member_result = await db.execute(
        select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.nickname == nickname,
            RoomMember.role == "player",
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=400, detail="You are not a player in this room")

    # Check if anyone from this team already answered
    team_answer = await db.execute(
        select(RoomAnswer).where(
            RoomAnswer.room_id == room.id,
            RoomAnswer.team == member.team,
            RoomAnswer.question_id == current_qid,
        )
    )
    if team_answer.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Your team already answered this question")

    q_result = await db.execute(select(Question).where(Question.id == current_qid))
    question = q_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    is_correct = req.option.upper() == question.correct_option
    answer = RoomAnswer(
        room_id=room.id,
        room_member_id=member.id,
        team=member.team,
        question_id=current_qid,
        selected_option=req.option.upper(),
        is_correct=is_correct,
    )
    db.add(answer)

    # Scores are deferred — calculated on reveal, not on answer

    room.last_activity_at = utcnow()
    db.add(room)
    await db.commit()

    return {"is_correct": is_correct, "team": member.team}


@router.post("/{code}/reset")
async def reset_room(
    code: str,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    from sqlalchemy import text

    await db.execute(text("DELETE FROM room_answers WHERE room_id = :rid"), {"rid": room.id})
    await db.execute(text("DELETE FROM room_members WHERE room_id = :rid"), {"rid": room.id})
    await db.execute(text("DELETE FROM rooms WHERE id = :rid"), {"rid": room.id})
    await db.commit()

    return {"ok": True}


@router.get("/{code}/state")
async def room_state(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.code == code.upper()))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    members_result = await db.execute(select(RoomMember).where(RoomMember.room_id == room.id))
    members = members_result.scalars().all()

    question_ids = room.get_questions_order()
    current_q = None
    if room.status == "active" and 0 <= room.current_question_index < len(question_ids):
        qid = question_ids[room.current_question_index]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if q:
            elapsed = 0.0
            if room.question_started_at:
                elapsed = (utcnow() - room.question_started_at).total_seconds()
            time_left = max(0, ANSWER_TIME_SECONDS - elapsed)
            current_q = {
                "id": q.id,
                "text": q.text,
                "image_url": q.image_url,
                "option_a": q.option_a,
                "option_b": q.option_b,
                "option_c": q.option_c,
                "option_d": q.option_d,
                "difficulty": q.difficulty,
                "time_left": round(time_left, 1),
                "index": room.current_question_index + 1,
                "total": len(question_ids),
            }

    # Check for reveal
    correct_reveal = None
    if room.status == "active" and room.current_question_index >= 0:
        elapsed = 0.0
        if room.question_started_at:
            elapsed = (utcnow() - room.question_started_at).total_seconds()
        if elapsed >= ANSWER_TIME_SECONDS:
            qid = question_ids[room.current_question_index]
            q_result = await db.execute(select(Question).where(Question.id == qid))
            q = q_result.scalar_one_or_none()
            if q:
                ans_result = await db.execute(
                    select(RoomAnswer).where(
                        RoomAnswer.room_id == room.id,
                        RoomAnswer.question_id == q.id,
                    )
                )
                all_answers = ans_result.scalars().all()
                answer_details = []
                for a in all_answers:
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
                correct_reveal = {
                    "correct_option": q.correct_option,
                    "explanation": q.explanation,
                    "answers": answer_details,
                }

    topic_name = None
    if room.topic_id:
        t_result = await db.execute(select(Topic).where(Topic.id == room.topic_id))
        topic = t_result.scalar_one_or_none()
        if topic:
            topic_name = topic.name

    team_a_score = sum(m.score for m in members if m.team == "A" and m.role == "player")
    team_b_score = sum(m.score for m in members if m.team == "B" and m.role == "player")

    return {
        "status": room.status,
        "code": room.code,
        "name": room.name or f"Комната {room.id}",
        "is_private": room.is_private,
        "topic": topic_name,
        "topic_id": room.topic_id,
        "current_question": current_q,
        "team_a": {
            "score": team_a_score,
            "members": [{"id": m.id, "nickname": m.nickname} for m in members if m.team == "A" and m.role == "player"],
        },
        "team_b": {
            "score": team_b_score,
            "members": [{"id": m.id, "nickname": m.nickname} for m in members if m.team == "B" and m.role == "player"],
        },
        "observers": [{"id": m.id, "nickname": m.nickname} for m in members if m.role == "observer"],
        "correct_reveal": correct_reveal,
    }
