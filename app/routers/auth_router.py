import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_player, hash_password, verify_password
from app.database import get_db
from app.models import Player, Team

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEFAULT_AVATARS = [
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48Y2lyY2xlIGN4PSI1MCIgY3k9IjUwIiByPSI0OCIgZmlsbD0iI0ZGRDcwMCIvPjxjaXJjbGUgY3g9IjM1IiBjeT0iNDAiIHI9IjciIGZpbGw9IiMzMzMiLz48Y2lyY2xlIGN4PSI2NSIgY3k9IjQwIiByPSI3IiBmaWxsPSIjMzMzIi8+PGVsbGlwc2UgY3g9IjUwIiBjeT0iNjUiIHJ4PSIxNSIgcnk9IjEwIiBmaWxsPSJub25lIiBzdHJva2U9IiMzMzMiIHN0cm9rZS13aWR0aD0iMyIvPjwvc3ZnPg==",
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48Y2lyY2xlIGN4PSI1MCIgY3k9IjUwIiByPSI0OCIgZmlsbD0iIzRFRDhGNSIvPjxjaXJjbGUgY3g9IjM1IiBjeT0iNDAiIHI9IjciIGZpbGw9IiMzMzMiLz48Y2lyY2xlIGN4PSI2NSIgY3k9IjQwIiByPSI3IiBmaWxsPSIjMzMzIi8+PHBhdGggZD0iTTM1IDY1IFE1MCA4MCA2NSA2NSIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjMzMzIiBzdHJva2Utd2lkdGg9IjMiLz48L3N2Zz4=",
]

FUNNY_NAMES = ["Команда Почемучек", "Знатоки с дивана"]


# --- Old team-based auth (kept for backward compat) ---


class RegisterRequest(BaseModel):
    name: str


class LoginRequest(BaseModel):
    name: str


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name too long")

    existing = await db.execute(select(Team).where(Team.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Team name already taken")

    team_count = await db.execute(select(Team))
    count = len(team_count.scalars().all())
    if count >= 2:
        raise HTTPException(status_code=400, detail="Maximum 2 teams allowed")

    avatar = DEFAULT_AVATARS[count % len(DEFAULT_AVATARS)]
    team = Team(name=name, avatar_url=avatar, score=0)
    db.add(team)
    await db.commit()
    await db.refresh(team)

    token = create_access_token({"team_id": team.id, "team_name": team.name})
    return {
        "token": token,
        "team": {"id": team.id, "name": team.name, "avatar_url": team.avatar_url, "score": team.score},
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.name == req.name.strip()))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    token = create_access_token({"team_id": team.id, "team_name": team.name})
    return {
        "token": token,
        "team": {"id": team.id, "name": team.name, "avatar_url": team.avatar_url, "score": team.score},
    }


@router.get("/teams")
async def list_teams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team))
    teams = result.scalars().all()
    return [{"id": t.id, "name": t.name, "avatar_url": t.avatar_url, "score": t.score} for t in teams]


# --- New player-based auth ---


class PlayerRegisterRequest(BaseModel):
    nickname: str
    email: str
    password: str


class PlayerLoginRequest(BaseModel):
    email: str
    password: str


class GuestRequest(BaseModel):
    nickname: str


@router.post("/player/register")
async def player_register(req: PlayerRegisterRequest, db: AsyncSession = Depends(get_db)):
    nickname = req.nickname.strip()
    email = req.email.strip().lower()
    password = req.password

    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname cannot be empty")
    if len(nickname) > 100:
        raise HTTPException(status_code=400, detail="Nickname too long")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    existing = await db.execute(select(Player).where(Player.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    player = Player(
        nickname=nickname,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)

    token = create_access_token(
        {
            "player_id": player.id,
            "nickname": player.nickname,
            "is_registered": True,
        }
    )
    return {
        "token": token,
        "player": {
            "id": player.id,
            "nickname": player.nickname,
            "email": player.email,
            "total_score": player.total_score,
            "games_played": player.games_played,
        },
    }


@router.post("/player/login")
async def player_login(req: PlayerLoginRequest, db: AsyncSession = Depends(get_db)):
    email = req.email.strip().lower()
    result = await db.execute(select(Player).where(Player.email == email))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if not verify_password(req.password, player.password_hash):
        raise HTTPException(status_code=401, detail="Wrong password")

    token = create_access_token(
        {
            "player_id": player.id,
            "nickname": player.nickname,
            "is_registered": True,
        }
    )
    return {
        "token": token,
        "player": {
            "id": player.id,
            "nickname": player.nickname,
            "email": player.email,
            "total_score": player.total_score,
            "games_played": player.games_played,
        },
    }


@router.post("/guest")
async def guest_login(req: GuestRequest):
    nickname = req.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname cannot be empty")
    if len(nickname) > 100:
        raise HTTPException(status_code=400, detail="Nickname too long")

    guest_id = str(uuid.uuid4())[:8]
    token = create_access_token(
        {
            "nickname": nickname,
            "is_registered": False,
            "guest_id": guest_id,
        }
    )
    return {
        "token": token,
        "player": {
            "nickname": nickname,
            "is_registered": False,
        },
    }


@router.get("/me")
async def get_me(player: dict = Depends(get_current_player)):
    return {
        "nickname": player.get("nickname"),
        "is_registered": player.get("is_registered", False),
        "player_id": player.get("player_id"),
    }
