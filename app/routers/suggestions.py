
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_player
from app.database import get_db
from app.models import SuggestedTopic, TopicVote

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


class SuggestRequest(BaseModel):
    name: str


class VoteRequest(BaseModel):
    vote: int  # +1 or -1


@router.get("")
async def list_suggestions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SuggestedTopic))
    topics = result.scalars().all()

    items = []
    for t in topics:
        rating_result = await db.execute(
            select(func.coalesce(func.sum(TopicVote.vote), 0)).where(TopicVote.suggested_topic_id == t.id)
        )
        rating = rating_result.scalar() or 0
        items.append({
            "id": t.id,
            "name": t.name,
            "suggested_by": t.suggested_by,
            "rating": rating,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    items.sort(key=lambda x: x["rating"], reverse=True)
    return items


@router.post("")
async def create_suggestion(
    req: SuggestRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    name = req.name.strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=400, detail="Название должно быть от 1 до 120 символов")

    topic = SuggestedTopic(
        name=name,
        suggested_by=player.get("nickname", "Unknown"),
        player_id=player.get("player_id"),
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return {"id": topic.id, "name": topic.name}


@router.post("/{topic_id}/vote")
async def vote_suggestion(
    topic_id: int,
    req: VoteRequest,
    player: dict = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    if req.vote not in (1, -1):
        raise HTTPException(status_code=400, detail="Vote must be +1 or -1")

    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    nickname = player.get("nickname", "Unknown")

    existing = await db.execute(
        select(TopicVote).where(
            TopicVote.suggested_topic_id == topic_id,
            TopicVote.player_nickname == nickname,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Вы уже голосовали")

    vote = TopicVote(
        suggested_topic_id=topic_id,
        player_nickname=nickname,
        vote=req.vote,
    )
    db.add(vote)
    await db.commit()
    return {"ok": True}
