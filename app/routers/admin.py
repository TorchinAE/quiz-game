import glob
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import create_access_token, get_admin_token, verify_admin, verify_token
from app.database import get_db
from app.models import Player, Question, Room, Topic, VisitStats

router = APIRouter(tags=["admin"])

PICTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "pictures")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TopicCreate(BaseModel):
    name: str
    description: str = ""
    image_url: str = ""


class TopicUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    image_url: str | None = None


class QuestionCreate(BaseModel):
    topic_id: int
    text: str
    image_url: str = ""
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    explanation: str = ""
    difficulty: int = 1


class QuestionUpdate(BaseModel):
    topic_id: int | None = None
    text: str | None = None
    image_url: str | None = None
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    correct_option: str | None = None
    explanation: str | None = None
    difficulty: int | None = None


def require_admin(request: Request):
    token = get_admin_token(request)
    payload = verify_token(token) if token else None
    if not payload or not payload.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


@router.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    if not verify_admin(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"is_admin": True, "username": req.username})
    return {"token": token}


# --- Topics CRUD ---


@router.get("/api/admin/topics")
async def list_topics(request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Topic).options(selectinload(Topic.questions)))
    topics = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "image_url": t.image_url,
            "is_active": t.is_active,
            "question_count": len(t.questions),
            "active_question_count": sum(1 for q in t.questions if q.is_active),
        }
        for t in topics
    ]


@router.post("/api/admin/topics")
async def create_topic(req: TopicCreate, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    topic = Topic(name=req.name, description=req.description, image_url=req.image_url)
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return {"id": topic.id, "name": topic.name, "description": topic.description, "image_url": topic.image_url}


@router.put("/api/admin/topics/{topic_id}")
async def update_topic(topic_id: int, req: TopicUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    if req.name is not None:
        topic.name = req.name
    if req.description is not None:
        topic.description = req.description
    if req.image_url is not None:
        topic.image_url = req.image_url
    await db.commit()
    return {"id": topic.id, "name": topic.name, "description": topic.description, "image_url": topic.image_url}


@router.delete("/api/admin/topics/{topic_id}")
async def delete_topic(topic_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    await db.delete(topic)
    await db.commit()
    return {"ok": True}


# --- Questions CRUD ---


@router.get("/api/admin/questions")
async def list_questions(request: Request, topic_id: int | None = None, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    q = select(Question)
    if topic_id:
        q = q.where(Question.topic_id == topic_id)
    result = await db.execute(q)
    questions = result.scalars().all()
    return [_question_dict(q) for q in questions]


@router.post("/api/admin/questions")
async def create_question(req: QuestionCreate, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    if req.correct_option.upper() not in ("A", "B", "C", "D"):
        raise HTTPException(status_code=400, detail="correct_option must be A, B, C, or D")
    if req.difficulty not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="difficulty must be 1, 2, or 3")
    question = Question(
        topic_id=req.topic_id,
        text=req.text,
        image_url=req.image_url,
        option_a=req.option_a,
        option_b=req.option_b,
        option_c=req.option_c,
        option_d=req.option_d,
        correct_option=req.correct_option.upper(),
        explanation=req.explanation,
        difficulty=req.difficulty,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return _question_dict(question)


@router.put("/api/admin/questions/{question_id}")
async def update_question(question_id: int, req: QuestionUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    for field in (
        "topic_id",
        "text",
        "image_url",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_option",
        "explanation",
        "difficulty",
    ):
        val = getattr(req, field, None)
        if val is not None:
            if field == "correct_option":
                val = val.upper()
                if val not in ("A", "B", "C", "D"):
                    raise HTTPException(status_code=400, detail="correct_option must be A, B, C, or D")
            setattr(question, field, val)
    await db.commit()
    return _question_dict(question)


@router.delete("/api/admin/questions/{question_id}")
async def delete_question(question_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.delete(question)
    await db.commit()
    return {"ok": True}


def _question_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "topic_id": q.topic_id,
        "text": q.text,
        "image_url": q.image_url,
        "option_a": q.option_a,
        "option_b": q.option_b,
        "option_c": q.option_c,
        "option_d": q.option_d,
        "correct_option": q.correct_option,
        "explanation": q.explanation,
        "difficulty": q.difficulty,
        "is_active": q.is_active,
    }


# --- Toggle active ---


@router.put("/api/admin/topics/{topic_id}/toggle")
async def toggle_topic(topic_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.is_active = not topic.is_active
    await db.commit()
    return {"id": topic.id, "is_active": topic.is_active}


@router.put("/api/admin/questions/{question_id}/toggle")
async def toggle_question(question_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.is_active = not question.is_active
    await db.commit()
    return {"id": question.id, "is_active": question.is_active}


# --- Image management ---


@router.post("/api/admin/upload-image")
async def upload_image(request: Request, file: UploadFile):
    require_admin(request)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Недопустимый формат: {ext}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс 5MB)")

    filename = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(PICTURES_DIR, exist_ok=True)
    filepath = os.path.join(PICTURES_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    return {"filename": filename, "url": f"/pictures/{filename}"}


@router.get("/api/admin/images")
async def list_images(request: Request):
    require_admin(request)
    os.makedirs(PICTURES_DIR, exist_ok=True)
    files = []
    for f in sorted(os.listdir(PICTURES_DIR)):
        ext = os.path.splitext(f)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            files.append({"filename": f, "url": f"/pictures/{f}"})
    return files


@router.delete("/api/admin/images/{filename}")
async def delete_image(filename: str, request: Request):
    require_admin(request)
    filepath = os.path.join(PICTURES_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(filepath)
    return {"ok": True}


# --- Stats ---


@router.get("/api/admin/stats")
async def get_stats(request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    total_visits = (await db.execute(select(func.count(VisitStats.id)))).scalar() or 0
    unique_players = (await db.execute(
        select(func.count(func.distinct(VisitStats.player_nickname)))
        .where(VisitStats.player_nickname.isnot(None))
    )).scalar() or 0
    total_rooms = (await db.execute(select(func.count(Room.id)))).scalar() or 0
    active_rooms = (await db.execute(
        select(func.count(Room.id)).where(Room.status.in_(["waiting", "active"]))
    )).scalar() or 0
    total_players = (await db.execute(select(func.count(Player.id)))).scalar() or 0
    total_games_finished = (await db.execute(
        select(func.count(Room.id)).where(Room.status == "finished")
    )).scalar() or 0

    return {
        "total_visits": total_visits,
        "unique_players": unique_players,
        "total_rooms": total_rooms,
        "active_rooms": active_rooms,
        "total_players": total_players,
        "total_games_finished": total_games_finished,
    }


@router.get("/api/admin/stats/visits")
async def get_visit_stats(request: Request, days: int = 30, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            func.date(VisitStats.visited_at).label("date"),
            func.count(VisitStats.id).label("count"),
        )
        .where(VisitStats.visited_at >= cutoff)
        .group_by(func.date(VisitStats.visited_at))
        .order_by(func.date(VisitStats.visited_at))
    )
    return [{"date": str(row.date), "count": row.count} for row in result.all()]


@router.get("/api/admin/stats/games")
async def get_game_stats(request: Request, days: int = 30, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            func.date(Room.started_at).label("date"),
            func.count(Room.id).label("count"),
        )
        .where(Room.started_at >= cutoff)
        .group_by(func.date(Room.started_at))
        .order_by(func.date(Room.started_at))
    )
    return [{"date": str(row.date), "count": row.count} for row in result.all()]


# --- Backup ---


BACKUP_DIR = "/tmp/quiz_backup"


@router.post("/api/admin/backup")
async def trigger_backup(request: Request):
    require_admin(request)
    from app.backup import create_backup, upload_backup

    path = await create_backup()
    await upload_backup(path)
    return {"ok": True, "path": path}


@router.get("/api/admin/backup/download")
async def download_backup(request: Request):
    require_admin(request)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    archives = sorted(glob.glob(os.path.join(BACKUP_DIR, "quiz_backup_*.tar.gz")))
    if not archives:
        raise HTTPException(status_code=404, detail="No backups found")
    latest = archives[-1]
    return FileResponse(latest, filename=os.path.basename(latest), media_type="application/gzip")
