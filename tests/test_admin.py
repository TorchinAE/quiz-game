import pytest

pytestmark = pytest.mark.asyncio


async def test_admin_crud_topics(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create
    res = await client.post(
        "/api/admin/topics", json={"name": "Тестовая тема", "description": "Описание"}, headers=headers
    )
    assert res.status_code == 200
    topic_id = res.json()["id"]

    # List
    res = await client.get("/api/admin/topics", headers=headers)
    assert res.status_code == 200
    assert any(t["name"] == "Тестовая тема" for t in res.json())

    # Update
    res = await client.put(f"/api/admin/topics/{topic_id}", json={"name": "Обновлённая тема"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Обновлённая тема"

    # Delete
    res = await client.delete(f"/api/admin/topics/{topic_id}", headers=headers)
    assert res.status_code == 200


async def test_admin_crud_questions(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create topic first
    topic_res = await client.post("/api/admin/topics", json={"name": "Q Topic"}, headers=headers)
    topic_id = topic_res.json()["id"]

    # Create question
    q_data = {
        "topic_id": topic_id,
        "text": "Тестовый вопрос?",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "B",
        "explanation": "Пояснение",
        "difficulty": 2,
    }
    res = await client.post("/api/admin/questions", json=q_data, headers=headers)
    assert res.status_code == 200
    q_id = res.json()["id"]
    assert res.json()["correct_option"] == "B"

    # List
    res = await client.get("/api/admin/questions", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # List by topic
    res = await client.get(f"/api/admin/questions?topic_id={topic_id}", headers=headers)
    assert res.status_code == 200

    # Update
    res = await client.put(f"/api/admin/questions/{q_id}", json={"text": "Обновлённый?"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["text"] == "Обновлённый?"

    # Delete
    res = await client.delete(f"/api/admin/questions/{q_id}", headers=headers)
    assert res.status_code == 200


async def test_admin_no_auth(client):
    res = await client.get("/api/admin/topics")
    assert res.status_code == 403


async def test_admin_invalid_correct_option(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    topic_res = await client.post("/api/admin/topics", json={"name": "T"}, headers=headers)
    topic_id = topic_res.json()["id"]

    res = await client.post(
        "/api/admin/questions",
        json={
            "topic_id": topic_id,
            "text": "Q?",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_option": "X",
        },
        headers=headers,
    )
    assert res.status_code == 400


async def test_admin_invalid_difficulty(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    topic_res = await client.post("/api/admin/topics", json={"name": "T2"}, headers=headers)
    topic_id = topic_res.json()["id"]

    res = await client.post(
        "/api/admin/questions",
        json={
            "topic_id": topic_id,
            "text": "Q?",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_option": "A",
            "difficulty": 5,
        },
        headers=headers,
    )
    assert res.status_code == 400


async def test_delete_nonexistent_topic(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.delete("/api/admin/topics/9999", headers=headers)
    assert res.status_code == 404


async def test_delete_nonexistent_question(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.delete("/api/admin/questions/9999", headers=headers)
    assert res.status_code == 404


async def test_update_question_invalid_correct(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    topic_res = await client.post("/api/admin/topics", json={"name": "T3"}, headers=headers)
    topic_id = topic_res.json()["id"]
    q_res = await client.post(
        "/api/admin/questions",
        json={
            "topic_id": topic_id,
            "text": "Q?",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_option": "A",
        },
        headers=headers,
    )
    q_id = q_res.json()["id"]
    res = await client.put(f"/api/admin/questions/{q_id}", json={"correct_option": "Z"}, headers=headers)
    assert res.status_code == 400


async def test_update_topic_not_found(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.put("/api/admin/topics/9999", json={"name": "X"}, headers=headers)
    assert res.status_code == 404


async def test_update_question_not_found(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.put("/api/admin/questions/9999", json={"text": "X"}, headers=headers)
    assert res.status_code == 404


async def test_update_topic_all_fields(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.post(
        "/api/admin/topics", json={"name": "Full", "description": "D", "image_url": "http://img"}, headers=headers
    )
    tid = res.json()["id"]
    res = await client.put(
        f"/api/admin/topics/{tid}",
        json={"name": "Full2", "description": "D2", "image_url": "http://img2"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Full2"
    assert res.json()["description"] == "D2"


async def test_admin_questions_no_auth(client):
    res = await client.get("/api/admin/questions")
    assert res.status_code == 403


async def test_admin_create_question_no_auth(client):
    res = await client.post(
        "/api/admin/questions",
        json={
            "topic_id": 1,
            "text": "Q?",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_option": "A",
        },
    )
    assert res.status_code == 403
