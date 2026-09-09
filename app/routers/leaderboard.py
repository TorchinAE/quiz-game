from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Player

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("")
async def get_leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).order_by(Player.total_score.desc()).limit(5))
    players = result.scalars().all()
    return [
        {
            "nickname": p.nickname,
            "total_score": p.total_score,
            "games_played": p.games_played,
        }
        for p in players
    ]
