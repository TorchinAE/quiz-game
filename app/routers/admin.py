from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import create_access_token, get_admin_token, verify_admin, verify_token
from app.database import get_db
from app.models import Question, Topic

router = APIRouter(tags=["admin"])


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
            "question_count": len(t.questions),
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
    }
