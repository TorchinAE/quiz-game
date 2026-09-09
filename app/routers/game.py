import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_admin_token, get_current_team, verify_token
from app.config import ANSWER_TIME_SECONDS, QUESTIONS_PER_GAME
from app.database import get_db
from app.models import Game, Question, Team, TeamAnswer, Topic

router = APIRouter(prefix="/api/game", tags=["game"])


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AnswerRequest(BaseModel):
    question_id: int
    option: str


class StartRequest(BaseModel):
    topic_id: int


@router.get("/topics")
async def list_topics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic))
    topics = result.scalars().all()
    # Count questions per topic
    topics_data = []
    for t in topics:
        q_count = await db.execute(select(Question).where(Question.topic_id == t.id))
        count = len(q_count.scalars().all())
        topics_data.append({"id": t.id, "name": t.name, "description": t.description, "question_count": count})
    return topics_data


@router.get("/state")
async def game_state(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).order_by(Game.id.desc()))
    game = result.scalars().first()
    if not game:
        return {"status": "none"}

    teams_result = await db.execute(select(Team))
    teams = teams_result.scalars().all()

    question_ids = game.get_questions_order()
    current_q = None
    if game.status == "active" and 0 <= game.current_question_index < len(question_ids):
        qid = question_ids[game.current_question_index]
        q_result = await db.execute(select(Question).where(Question.id == qid))
        q = q_result.scalar_one_or_none()
        if q:
            elapsed = 0.0
            if game.question_started_at:
                elapsed = (utcnow() - game.question_started_at).total_seconds()
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
                "index": game.current_question_index + 1,
                "total": QUESTIONS_PER_GAME,
            }

    answers = []
    if current_q:
        ans_result = await db.execute(
            select(TeamAnswer).where(
                TeamAnswer.game_id == game.id,
                TeamAnswer.question_id == current_q["id"],
            )
        )
        answers = [{"team_id": a.team_id, "selected_option": a.selected_option} for a in ans_result.scalars().all()]

    correct_reveal = None
    if game.status == "active" and game.current_question_index >= 0:
        elapsed = 0.0
        if game.question_started_at:
            elapsed = (utcnow() - game.question_started_at).total_seconds()
        if elapsed >= ANSWER_TIME_SECONDS:
            qid = question_ids[game.current_question_index]
            q_result = await db.execute(select(Question).where(Question.id == qid))
            q = q_result.scalar_one_or_none()
            if q:
                ans_result = await db.execute(
                    select(TeamAnswer).where(
                        TeamAnswer.game_id == game.id,
                        TeamAnswer.question_id == q.id,
                    )
                )
                all_answers = ans_result.scalars().all()
                correct_reveal = {
                    "correct_option": q.correct_option,
                    "explanation": q.explanation,
                    "answers": [
                        {"team_id": a.team_id, "selected_option": a.selected_option, "is_correct": a.is_correct}
                        for a in all_answers
                    ],
                }

    topic_name = None
    if game.topic_id:
        t_result = await db.execute(select(Topic).where(Topic.id == game.topic_id))
        topic = t_result.scalar_one_or_none()
        if topic:
            topic_name = topic.name

    return {
        "status": game.status,
        "topic": topic_name,
        "current_question": current_q,
        "teams": [{"id": t.id, "name": t.name, "avatar_url": t.avatar_url, "score": t.score} for t in teams],
        "answers_received": [a["team_id"] for a in answers],
        "correct_reveal": correct_reveal,
    }


@router.post("/answer")
async def submit_answer(
    req: AnswerRequest,
    team: Team = Depends(get_current_team),
    db: AsyncSession = Depends(get_db),
):
    if req.option.upper() not in ("A", "B", "C", "D"):
        raise HTTPException(status_code=400, detail="Option must be A, B, C, or D")

    result = await db.execute(select(Game).order_by(Game.id.desc()))
    game = result.scalars().first()
    if not game or game.status != "active":
        raise HTTPException(status_code=400, detail="No active game")

    if game.question_started_at:
        elapsed = (utcnow() - game.question_started_at).total_seconds()
        if elapsed >= ANSWER_TIME_SECONDS:
            raise HTTPException(status_code=400, detail="Time is up")

    question_ids = game.get_questions_order()
    if game.current_question_index < 0 or game.current_question_index >= len(question_ids):
        raise HTTPException(status_code=400, detail="No current question")

    current_qid = question_ids[game.current_question_index]

    existing = await db.execute(
        select(TeamAnswer).where(
            TeamAnswer.game_id == game.id,
            TeamAnswer.team_id == team.id,
            TeamAnswer.question_id == current_qid,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already answered")

    q_result = await db.execute(select(Question).where(Question.id == current_qid))
    question = q_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    is_correct = req.option.upper() == question.correct_option
    answer = TeamAnswer(
        game_id=game.id,
        team_id=team.id,
        question_id=current_qid,
        selected_option=req.option.upper(),
        is_correct=is_correct,
    )
    db.add(answer)

    if is_correct:
        team.score += question.difficulty
        db.add(team)

    await db.commit()

    # Broadcast updated scores to all clients
    from app.routers.ws import broadcast_scores

    await broadcast_scores()

    return {"is_correct": is_correct, "score": team.score}


@router.post("/start")
async def start_game(req: StartRequest, request: Request, db: AsyncSession = Depends(get_db)):
    token = get_admin_token(request)
    is_admin = False
    if token:
        payload = verify_token(token)
        is_admin = payload and payload.get("is_admin")

    if not is_admin:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            payload = verify_token(auth[7:])
            if not payload or "team_id" not in payload:
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    # Verify topic exists
    topic_result = await db.execute(select(Topic).where(Topic.id == req.topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    teams_result = await db.execute(select(Team))
    teams = teams_result.scalars().all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need 2 teams to start")

    for t in teams:
        t.score = 0
        db.add(t)

    # Filter questions by selected topic
    q_result = await db.execute(select(Question).where(Question.topic_id == req.topic_id))
    all_questions = q_result.scalars().all()
    if len(all_questions) < QUESTIONS_PER_GAME:
        raise HTTPException(
            status_code=400, detail=f"Topic has {len(all_questions)} questions, need at least {QUESTIONS_PER_GAME}"
        )

    selected = random.sample(list(all_questions), QUESTIONS_PER_GAME)
    question_ids = [q.id for q in selected]

    game = Game(status="active", topic_id=req.topic_id, current_question_index=-1)
    game.set_questions_order(question_ids)
    game.started_at = utcnow()
    db.add(game)
    await db.commit()
    await db.refresh(game)

    return {"game_id": game.id, "status": "active", "topic": topic.name, "questions_count": len(question_ids)}


@router.post("/next")
async def next_question(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).order_by(Game.id.desc()))
    game = result.scalars().first()
    if not game or game.status != "active":
        raise HTTPException(status_code=400, detail="No active game")

    question_ids = game.get_questions_order()
    next_idx = game.current_question_index + 1

    if next_idx >= len(question_ids):
        game.status = "finished"
        await db.commit()
        from app.routers.ws import broadcast_game_over

        await broadcast_game_over()
        return {"status": "finished"}

    game.current_question_index = next_idx
    game.question_started_at = utcnow()
    await db.commit()

    # Broadcast new question to all clients
    from app.routers.ws import broadcast_question

    await broadcast_question(game.id)

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


@router.get("/results")
async def game_results(db: AsyncSession = Depends(get_db)):
    teams_result = await db.execute(select(Team).order_by(Team.score.desc()))
    teams = teams_result.scalars().all()
    return {
        "teams": [{"id": t.id, "name": t.name, "avatar_url": t.avatar_url, "score": t.score} for t in teams],
    }


@router.post("/reset")
async def reset_game(request: Request, db: AsyncSession = Depends(get_db)):
    token = get_admin_token(request)
    is_admin = False
    if token:
        payload = verify_token(token)
        is_admin = payload and payload.get("is_admin")
    if not is_admin:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            payload = verify_token(auth[7:])
            if not payload or "team_id" not in payload:
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    from sqlalchemy import text

    await db.execute(text("DELETE FROM team_answers"))
    await db.execute(text("DELETE FROM games"))
    teams_result = await db.execute(select(Team))
    for t in teams_result.scalars().all():
        t.score = 0
        db.add(t)
    await db.commit()
    return {"ok": True}
