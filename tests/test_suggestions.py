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


async def approve_topic(client, topic_id):
    """Helper: approve a pending topic."""
    res = await client.post(f"/api/suggestions/{topic_id}/approve")
    assert res.status_code == 200


async def test_suggest_topic(client):
    reg = await register_player(client, "Предложик")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/suggestions", json={"name": "Космос"}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Космос"
    assert data["status"] == "pending"
    assert "id" in data


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


async def test_list_suggestions_only_approved(client):
    reg = await register_player(client, "Списочник")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r1 = await client.post("/api/suggestions", json={"name": "История"}, headers=headers)
    r2 = await client.post("/api/suggestions", json={"name": "Наука"}, headers=headers)
    tid1 = r1.json()["id"]
    tid2 = r2.json()["id"]

    # Before approval — empty list
    res = await client.get("/api/suggestions")
    assert res.status_code == 200
    assert len(res.json()) == 0

    # Approve both
    await approve_topic(client, tid1)
    await approve_topic(client, tid2)

    res = await client.get("/api/suggestions")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2
    assert all("name" in s and "rating" in s for s in items)


async def test_pending_not_voteable(client):
    reg = await register_player(client, "РаннийПтица")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r = await client.post("/api/suggestions", json={"name": "Музыка"}, headers=headers)
    tid = r.json()["id"]

    # Can't vote on pending topic
    res = await client.post(f"/api/suggestions/{tid}/vote", json={"vote": 1}, headers=headers)
    assert res.status_code == 404


async def test_vote_up(client):
    reg = await register_player(client, "Голосовщик")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r = await client.post("/api/suggestions", json={"name": "Музыка"}, headers=headers)
    tid = r.json()["id"]
    await approve_topic(client, tid)

    res = await client.post(f"/api/suggestions/{tid}/vote", json={"vote": 1}, headers=headers)
    assert res.status_code == 200


async def test_vote_down(client):
    reg = await register_player(client, "Минусовщик")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r = await client.post("/api/suggestions", json={"name": "Скучная тема"}, headers=headers)
    tid = r.json()["id"]
    await approve_topic(client, tid)

    res = await client.post(f"/api/suggestions/{tid}/vote", json={"vote": -1}, headers=headers)
    assert res.status_code == 200


async def test_vote_duplicate_rejected(client):
    reg = await register_player(client, "ДубльГолос")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r = await client.post("/api/suggestions", json={"name": "Философия"}, headers=headers)
    tid = r.json()["id"]
    await approve_topic(client, tid)

    await client.post(f"/api/suggestions/{tid}/vote", json={"vote": 1}, headers=headers)
    res = await client.post(f"/api/suggestions/{tid}/vote", json={"vote": -1}, headers=headers)
    assert res.status_code == 400


async def test_approve_and_reject(client):
    reg = await register_player(client, "Админов")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r = await client.post("/api/suggestions", json={"name": "Тест тема"}, headers=headers)
    tid = r.json()["id"]

    # Approve
    res = await client.post(f"/api/suggestions/{tid}/approve")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    # Reject
    res = await client.post(f"/api/suggestions/{tid}/reject")
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    # Rejected not in list
    items = (await client.get("/api/suggestions")).json()
    assert all(s["id"] != tid for s in items)


async def test_edit_suggestion(client):
    reg = await register_player(client, "Редактор")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    r = await client.post("/api/suggestions", json={"name": "Старое название"}, headers=headers)
    tid = r.json()["id"]

    res = await client.put(f"/api/suggestions/{tid}", json={"name": "Новое название"})
    assert res.status_code == 200
    assert res.json()["name"] == "Новое название"


async def test_vote_no_auth(client):
    res = await client.post("/api/suggestions/1/vote", json={"vote": 1})
    assert res.status_code in (401, 403)


async def test_suggest_topic_no_auth(client):
    res = await client.post("/api/suggestions", json={"name": "Тема"})
    assert res.status_code in (401, 403)
