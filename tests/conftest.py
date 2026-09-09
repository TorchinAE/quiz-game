import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use test database
os.environ["QUIZ_DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_quiz.db"

from app.database import Base, engine
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Clean up test db
    if os.path.exists("./data/test_quiz.db"):
        os.remove("./data/test_quiz.db")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token(client):
    res = await client.post("/api/admin/login", json={"username": "k2k1", "password": "123123"})
    return res.json()["token"]


@pytest_asyncio.fixture
async def two_teams(client):
    teams = []
    for name in ["Тестовые Тигры", "Проверенные Пингвины"]:
        res = await client.post("/api/auth/register", json={"name": name})
        assert res.status_code == 200
        teams.append(res.json())
    return teams
