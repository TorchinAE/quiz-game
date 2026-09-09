import pytest

pytestmark = pytest.mark.asyncio


async def test_leaderboard_empty(client):
    res = await client.get("/api/leaderboard")
    assert res.status_code == 200
    assert res.json() == []


async def test_leaderboard_with_players(client):
    # Register players
    for i in range(3):
        await client.post(
            "/api/auth/player/register",
            json={
                "nickname": f"Лидер{i}",
                "email": f"leader{i}@test.com",
                "password": "pass1234",
            },
        )

    res = await client.get("/api/leaderboard")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    for p in data:
        assert "nickname" in p
        assert "total_score" in p
        assert "games_played" in p


async def test_leaderboard_limit(client):
    # Register 7 players — leaderboard should return top 5
    for i in range(7):
        await client.post(
            "/api/auth/player/register",
            json={
                "nickname": f"Топ{i}",
                "email": f"top{i}@test.com",
                "password": "pass1234",
            },
        )

    res = await client.get("/api/leaderboard")
    assert res.status_code == 200
    assert len(res.json()) == 5
