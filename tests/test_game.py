import pytest

from app.database import async_session
from app.models import Question, Topic

pytestmark = pytest.mark.asyncio


async def seed_questions(count=15):
    """Seed test questions into DB. Returns topic_id."""
    async with async_session() as db:
        topic = Topic(name="Тестовая тема", description="Для тестов")
        db.add(topic)
        await db.commit()
        await db.refresh(topic)
        topic_id = topic.id

        for i in range(count):
            q = Question(
                topic_id=topic_id,
                text=f"Вопрос {i + 1}?",
                option_a="Ответ A",
                option_b="Ответ B",
                option_c="Ответ C",
                option_d="Ответ D",
                correct_option="A",
                explanation=f"Пояснение {i + 1}",
                difficulty=(i % 3) + 1,
            )
            db.add(q)
        await db.commit()
        return topic_id


async def test_game_state_no_game(client):
    res = await client.get("/api/game/state")
    assert res.status_code == 200
    assert res.json()["status"] == "none"


async def test_list_topics(client):
    await seed_questions()
    res = await client.get("/api/game/topics")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["question_count"] == 15


async def test_start_game_admin(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert data["questions_count"] == 12
    assert data["topic"] == "Тестовая тема"


async def test_start_game_team(client, two_teams):
    topic_id = await seed_questions()
    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "active"


async def test_start_game_no_teams(client, admin_token):
    topic_id = await seed_questions()
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers)
    assert res.status_code == 400
    assert "2 teams" in res.json()["detail"]


async def test_start_game_not_enough_questions(client, admin_token, two_teams):
    # Create topic with only 5 questions
    topic_id = await seed_questions(count=5)
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers)
    assert res.status_code == 400
    assert "questions" in res.json()["detail"].lower()


async def test_start_game_topic_not_found(client, admin_token, two_teams):
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post("/api/game/start", json={"topic_id": 9999}, headers=headers)
    assert res.status_code == 404


async def test_start_game_no_auth(client, two_teams):
    topic_id = await seed_questions()
    res = await client.post("/api/game/start", json={"topic_id": topic_id})
    assert res.status_code == 403


async def test_next_question(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers)

    res = await client.post("/api/game/next", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert data["question"] is not None
    assert data["question"]["index"] == 1
    assert data["question"]["total"] == 12


async def test_game_state_after_start(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers)
    await client.post("/api/game/next", headers=headers)

    res = await client.get("/api/game/state")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert data["topic"] == "Тестовая тема"
    assert data["current_question"] is not None
    assert data["current_question"]["index"] == 1
    assert len(data["teams"]) == 2


async def test_submit_answer_correct(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/game/answer", json={"question_id": 1, "option": "A"}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_correct"] is True
    assert data["score"] > 0


async def test_submit_answer_wrong(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/game/answer", json={"question_id": 1, "option": "B"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["is_correct"] is False
    assert res.json()["score"] == 0


async def test_submit_answer_duplicate(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/game/answer", json={"question_id": 1, "option": "A"}, headers=headers)
    res = await client.post("/api/game/answer", json={"question_id": 1, "option": "A"}, headers=headers)
    assert res.status_code == 400
    assert "already" in res.json()["detail"].lower()


async def test_submit_answer_invalid_option(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/game/answer", json={"question_id": 1, "option": "X"}, headers=headers)
    assert res.status_code == 400


async def test_submit_answer_no_game(client, two_teams):
    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/game/answer", json={"question_id": 1, "option": "A"}, headers=headers)
    assert res.status_code == 400
    assert "no active game" in res.json()["detail"].lower()


async def test_submit_answer_no_auth(client):
    res = await client.post("/api/game/answer", json={"question_id": 1, "option": "A"})
    assert res.status_code == 401


async def test_game_results(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    # Both teams answer
    for i, team in enumerate(two_teams):
        headers = {"Authorization": f"Bearer {team['token']}"}
        option = "A" if i == 0 else "B"
        await client.post("/api/game/answer", json={"question_id": 1, "option": option}, headers=headers)

    res = await client.get("/api/game/results")
    assert res.status_code == 200
    data = res.json()
    assert len(data["teams"]) == 2
    # First team answered correctly (A), second didn't (B)
    scores = {t["name"]: t["score"] for t in data["teams"]}
    assert scores["Тестовые Тигры"] > scores["Проверенные Пингвины"]


async def test_finish_game(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)

    # Advance through all 12 questions
    for _ in range(12):
        res = await client.post("/api/game/next", headers=headers_admin)
        assert res.status_code == 200

    # Next one should finish the game
    res = await client.post("/api/game/next", headers=headers_admin)
    assert res.status_code == 200
    assert res.json()["status"] == "finished"


async def test_next_question_no_game(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.post("/api/game/next", headers=headers)
    assert res.status_code == 400


async def test_reset_game(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    # Answer something
    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/game/answer", json={"question_id": 1, "option": "A"}, headers=headers)

    # Reset
    res = await client.post("/api/game/reset", headers=headers_admin)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verify clean state
    res = await client.get("/api/game/state")
    assert res.json()["status"] == "none"

    res = await client.get("/api/game/results")
    for t in res.json()["teams"]:
        assert t["score"] == 0


async def test_reset_game_team_auth(client, two_teams):
    await seed_questions()
    token = two_teams[0]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/game/reset", headers=headers)
    assert res.status_code == 200


async def test_reset_game_no_auth(client):
    res = await client.post("/api/game/reset")
    assert res.status_code == 403


async def test_both_teams_answer_same_question(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    for team in two_teams:
        headers = {"Authorization": f"Bearer {team['token']}"}
        await client.post("/api/game/answer", json={"question_id": 1, "option": "A"}, headers=headers)

    # Check state shows both answered
    res = await client.get("/api/game/state")
    data = res.json()
    assert len(data["answers_received"]) == 2


async def test_game_state_teams_info(client, admin_token, two_teams):
    topic_id = await seed_questions()
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    await client.post("/api/game/start", json={"topic_id": topic_id}, headers=headers_admin)
    await client.post("/api/game/next", headers=headers_admin)

    res = await client.get("/api/game/state")
    data = res.json()
    for t in data["teams"]:
        assert "id" in t
        assert "name" in t
        assert "score" in t
        assert "avatar_url" in t
