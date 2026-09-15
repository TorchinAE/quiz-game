import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
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
    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.status == "approved"))
    topics = result.scalars().all()

    items = []
    for t in topics:
        rating_result = await db.execute(
            select(func.coalesce(func.sum(TopicVote.vote), 0)).where(TopicVote.suggested_topic_id == t.id)
        )
        rating = rating_result.scalar() or 0
        items.append(
            {
                "id": t.id,
                "name": t.name,
                "suggested_by": t.suggested_by,
                "rating": rating,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
        )

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
        status="pending",
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)

    # Notify admin via Telegram (fire-and-forget)
    try:
        from app.telegram_bot import notify_suggestion_pending

        asyncio.create_task(notify_suggestion_pending(topic.id, topic.name, topic.suggested_by))
    except Exception:
        pass

    # Notify admin via email (background)
    try:
        from app.email_notifier import notify_suggestion_pending_email_in_background

        notify_suggestion_pending_email_in_background(
            topic.id,
            topic.name,
            topic.suggested_by,
            created_at=topic.created_at,
            votes_up=0,
            votes_down=0,
        )
    except Exception:
        pass

    return {"id": topic.id, "name": topic.name, "status": topic.status}


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
    if topic.status != "approved":
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


@router.post("/{topic_id}/approve")
async def approve_suggestion(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    topic.status = "approved"
    await db.commit()
    return {"ok": True, "status": "approved"}


@router.post("/{topic_id}/reject")
async def reject_suggestion(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    topic.status = "rejected"
    await db.commit()
    return {"ok": True, "status": "rejected"}


def _confirmation_page(title: str, message: str, color: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body{{font-family:'Segoe UI',Tahoma,sans-serif;background:#1a1a2e;color:#eee;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{background:#16213e;border-radius:16px;padding:40px;text-align:center;
max-width:420px;box-shadow:0 4px 20px rgba(0,0,0,.3)}}
h2{{color:{color};margin:0 0 12px}}p{{color:#888;line-height:1.5}}
a{{color:#0f9dce;text-decoration:none}}a:hover{{text-decoration:underline}}
</style></head><body><div class="box"><h2>{title}</h2><p>{message}</p>
<p><a href="/quiz/lobby">Перейти в лобби</a></p></div></body></html>"""
    )


@router.get("/{topic_id}/approve")
async def approve_suggestion_link(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        return _confirmation_page("Ошибка", "Тема не найдена", "#e94560")

    topic.status = "approved"
    await db.commit()
    return _confirmation_page("Тема одобрена", f"«{topic.name}» одобрена и теперь доступна для голосования.", "#00b894")


@router.get("/{topic_id}/reject")
async def reject_suggestion_link(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        return _confirmation_page("Ошибка", "Тема не найдена", "#e94560")

    topic.status = "rejected"
    await db.commit()
    return _confirmation_page("Тема отклонена", f"«{topic.name}» отклонена.", "#e94560")


class EditRequest(BaseModel):
    name: str


@router.put("/{topic_id}")
async def edit_suggestion(
    topic_id: int,
    req: EditRequest,
    db: AsyncSession = Depends(get_db),
):
    name = req.name.strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=400, detail="Название должно быть от 1 до 120 символов")

    result = await db.execute(select(SuggestedTopic).where(SuggestedTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    topic.name = name
    await db.commit()
    return {"ok": True, "name": topic.name}
