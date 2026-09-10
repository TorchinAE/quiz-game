import pytest

pytestmark = pytest.mark.asyncio


async def register_player(client, nickname="Игрок", email=None):
    if email is None:
        email = f"{nickname.lower().replace(' ', '_')}@test.com"
    res = await client.post(
        "/api/auth/player/register",
        json={"nickname": nickname, "email": email, "password": "pass1234"},
    )
    return res.json()


async def test_suggest_topic(client):
    reg = await register_player(client, "Предложик")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/suggestions", json={"name": "Космос"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Космос"
    assert "id" in res.json()


async def test_suggest_topic_max_length(client):
    reg = await register_player(client, "Длиннопис")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/suggestions", json={"name": "A" * 121}, headers=headers)
    assert res.status_code == 400


async def test_suggest_topic_120_chars_ok(client):
    reg = await register_player(client, "Точно120")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/suggestions", json={"name": "B" * 120}, headers=headers)
    assert res.status_code == 200


async def test_list_suggestions(client):
    reg = await register_player(client, "Списочник")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    await client.post("/api/suggestions", json={"name": "История"}, headers=headers)
    await client.post("/api/suggestions", json={"name": "Наука"}, headers=headers)

    res = await client.get("/api/suggestions")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2
    assert all("name" in s and "rating" in s for s in items)


async def test_vote_up(client):
    reg = await register_player(client, "Голосовщик")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    await client.post("/api/suggestions", json={"name": "Музыка"}, headers=headers)
    suggestions = (await client.get("/api/suggestions")).json()
    sid = suggestions[0]["id"]

    res = await client.post(f"/api/suggestions/{sid}/vote", json={"vote": 1}, headers=headers)
    assert res.status_code == 200


async def test_vote_down(client):
    reg = await register_player(client, "Минусовщик")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    await client.post("/api/suggestions", json={"name": "Скучная тема"}, headers=headers)
    suggestions = (await client.get("/api/suggestions")).json()
    sid = suggestions[0]["id"]

    res = await client.post(f"/api/suggestions/{sid}/vote", json={"vote": -1}, headers=headers)
    assert res.status_code == 200


async def test_vote_duplicate_rejected(client):
    reg = await register_player(client, "ДубльГолос")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    await client.post("/api/suggestions", json={"name": "Философия"}, headers=headers)
    suggestions = (await client.get("/api/suggestions")).json()
    sid = suggestions[0]["id"]

    await client.post(f"/api/suggestions/{sid}/vote", json={"vote": 1}, headers=headers)
    res = await client.post(f"/api/suggestions/{sid}/vote", json={"vote": -1}, headers=headers)
    assert res.status_code == 400


async def test_vote_no_auth(client):
    res = await client.post("/api/suggestions/1/vote", json={"vote": 1})
    assert res.status_code in (401, 403)


async def test_suggest_topic_no_auth(client):
    res = await client.post("/api/suggestions", json={"name": "Тема"})
    assert res.status_code in (401, 403)
