import pytest

pytestmark = pytest.mark.asyncio


async def test_register_team(client):
    res = await client.post("/api/auth/register", json={"name": "Крутые"})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["team"]["name"] == "Крутые"
    assert data["team"]["score"] == 0
    assert "avatar_url" in data["team"]


async def test_register_empty_name(client):
    res = await client.post("/api/auth/register", json={"name": ""})
    assert res.status_code == 400


async def test_register_duplicate(client):
    await client.post("/api/auth/register", json={"name": "Дубль"})
    res = await client.post("/api/auth/register", json={"name": "Дубль"})
    assert res.status_code == 400


async def test_register_max_teams(client):
    await client.post("/api/auth/register", json={"name": "Команда 1"})
    await client.post("/api/auth/register", json={"name": "Команда 2"})
    res = await client.post("/api/auth/register", json={"name": "Команда 3"})
    assert res.status_code == 400


async def test_login_team(client):
    await client.post("/api/auth/register", json={"name": "Логин"})
    res = await client.post("/api/auth/login", json={"name": "Логин"})
    assert res.status_code == 200
    assert "token" in res.json()


async def test_login_nonexistent(client):
    res = await client.post("/api/auth/login", json={"name": "Нет такой"})
    assert res.status_code == 404


async def test_list_teams(client, two_teams):
    res = await client.get("/api/auth/teams")
    assert res.status_code == 200
    assert len(res.json()) == 2


async def test_admin_login_success(client):
    res = await client.post("/api/admin/login", json={"username": "k2k1", "password": "123123"})
    assert res.status_code == 200
    assert "token" in res.json()


async def test_admin_login_fail(client):
    res = await client.post("/api/admin/login", json={"username": "k2k1", "password": "wrong"})
    assert res.status_code == 401


async def test_jwt_validity(client):
    res = await client.post("/api/auth/register", json={"name": "JWT Test"})
    token = res.json()["token"]
    # Use token to access protected endpoint
    game_res = await client.post(
        "/api/game/answer", json={"question_id": 1, "option": "A"}, headers={"Authorization": f"Bearer {token}"}
    )
    # Should get 400 (no active game) not 401 (unauthorized)
    assert game_res.status_code == 400


async def test_jwt_invalid(client):
    res = await client.post(
        "/api/game/answer", json={"question_id": 1, "option": "A"}, headers={"Authorization": "Bearer invalid_token"}
    )
    assert res.status_code == 401


async def test_register_long_name(client):
    res = await client.post("/api/auth/register", json={"name": "A" * 101})
    assert res.status_code == 400


async def test_register_whitespace_name(client):
    res = await client.post("/api/auth/register", json={"name": "   "})
    assert res.status_code == 400


async def test_login_whitespace_name(client):
    await client.post("/api/auth/register", json={"name": "SpaceTeam"})
    res = await client.post("/api/auth/login", json={"name": "  SpaceTeam  "})
    assert res.status_code == 200


async def test_register_returns_avatar(client):
    res = await client.post("/api/auth/register", json={"name": "Avatar Test"})
    assert res.status_code == 200
    assert res.json()["team"]["avatar_url"].startswith("data:image/svg")


async def test_no_auth_header(client):
    res = await client.get("/api/game/state")
    assert res.status_code == 200  # game state is public
