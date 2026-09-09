import pytest

pytestmark = pytest.mark.asyncio


async def test_player_register(client):
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Иван",
            "email": "ivan@test.com",
            "password": "pass1234",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["player"]["nickname"] == "Иван"
    assert data["player"]["email"] == "ivan@test.com"
    assert data["player"]["total_score"] == 0


async def test_player_register_duplicate_email(client):
    await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Иван",
            "email": "dup@test.com",
            "password": "pass1234",
        },
    )
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Другой",
            "email": "dup@test.com",
            "password": "pass1234",
        },
    )
    assert res.status_code == 400
    assert "already" in res.json()["detail"].lower()


async def test_player_register_invalid_email(client):
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Иван",
            "email": "noat",
            "password": "pass1234",
        },
    )
    assert res.status_code == 400
    assert "email" in res.json()["detail"].lower()


async def test_player_register_empty_email(client):
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Иван",
            "email": "",
            "password": "pass1234",
        },
    )
    assert res.status_code == 400


async def test_player_register_short_password(client):
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Иван",
            "email": "short@test.com",
            "password": "ab",
        },
    )
    assert res.status_code == 400
    assert "password" in res.json()["detail"].lower()


async def test_player_register_empty_nickname(client):
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "",
            "email": "empty@test.com",
            "password": "pass1234",
        },
    )
    assert res.status_code == 400
    assert "nickname" in res.json()["detail"].lower()


async def test_player_register_long_nickname(client):
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "A" * 101,
            "email": "long@test.com",
            "password": "pass1234",
        },
    )
    assert res.status_code == 400


async def test_player_login(client):
    await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Мария",
            "email": "maria@test.com",
            "password": "pass1234",
        },
    )
    res = await client.post(
        "/api/auth/player/login",
        json={
            "email": "maria@test.com",
            "password": "pass1234",
        },
    )
    assert res.status_code == 200
    assert "token" in res.json()
    assert res.json()["player"]["nickname"] == "Мария"


async def test_player_login_wrong_password(client):
    await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Петр",
            "email": "petr@test.com",
            "password": "pass1234",
        },
    )
    res = await client.post(
        "/api/auth/player/login",
        json={
            "email": "petr@test.com",
            "password": "wrong",
        },
    )
    assert res.status_code == 401


async def test_player_login_nonexistent(client):
    res = await client.post(
        "/api/auth/player/login",
        json={
            "email": "noone@test.com",
            "password": "pass1234",
        },
    )
    assert res.status_code == 404


async def test_guest_login(client):
    res = await client.post("/api/auth/guest", json={"nickname": "Гость"})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["player"]["nickname"] == "Гость"
    assert data["player"]["is_registered"] is False


async def test_guest_login_empty_nickname(client):
    res = await client.post("/api/auth/guest", json={"nickname": ""})
    assert res.status_code == 400


async def test_guest_login_long_nickname(client):
    res = await client.post("/api/auth/guest", json={"nickname": "A" * 101})
    assert res.status_code == 400


async def test_get_me_registered(client):
    reg = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": "Авторизован",
            "email": "auth@test.com",
            "password": "pass1234",
        },
    )
    token = reg.json()["token"]
    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["nickname"] == "Авторизован"
    assert res.json()["is_registered"] is True


async def test_get_me_guest(client):
    reg = await client.post("/api/auth/guest", json={"nickname": "Гостевод"})
    token = reg.json()["token"]
    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["nickname"] == "Гостевод"
    assert res.json()["is_registered"] is False


async def test_get_me_no_auth(client):
    res = await client.get("/api/auth/me")
    assert res.status_code == 401
