from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.database import async_session
from app.models import Question, Topic

pytestmark = pytest.mark.asyncio


async def seed_topic(count=15):
    """Create a topic with questions. Returns (topic_id, question_ids)."""
    async with async_session() as db:
        topic = Topic(name="Комнатная тема", description="Для тестов комнат")
        db.add(topic)
        await db.commit()
        await db.refresh(topic)
        topic_id = topic.id
        qids = []
        for i in range(count):
            q = Question(
                topic_id=topic_id,
                text=f"Комнатный вопрос {i + 1}?",
                option_a="A",
                option_b="B",
                option_c="C",
                option_d="D",
                correct_option="A",
                explanation=f"Пояснение {i + 1}",
                difficulty=(i % 3) + 1,
            )
            db.add(q)
        await db.commit()
        # Get question IDs
        result = await db.execute(select(Question).where(Question.topic_id == topic_id))
        qids = [q.id for q in result.scalars().all()]
        return topic_id, qids


async def register_player(client, nickname="Игрок", email=None):
    """Register a player and return token + player info."""
    if email is None:
        email = f"{nickname.lower().replace(' ', '_')}@test.com"
    res = await client.post(
        "/api/auth/player/register",
        json={
            "nickname": nickname,
            "email": email,
            "password": "pass1234",
        },
    )
    return res.json()


async def guest_login(client, nickname="Гость"):
    """Login as guest and return token + player info."""
    res = await client.post("/api/auth/guest", json={"nickname": nickname})
    return res.json()


async def create_and_join_room(client, topic_id, player_a_token, player_b_token):
    """Create a room, join two players, start game. Returns room code."""
    headers_a = {"Authorization": f"Bearer {player_a_token}"}
    headers_b = {"Authorization": f"Bearer {player_b_token}"}

    # Create room
    res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers_a)
    code = res.json()["code"]

    # Join as team A player
    await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers_a)
    # Join as team B player
    await client.post(f"/api/rooms/{code}/join", json={"team": "B", "role": "player"}, headers=headers_b)

    # Start game
    await client.post(f"/api/rooms/{code}/start", json={"topic_id": topic_id}, headers=headers_a)

    return code


# --- Room CRUD ---


async def test_create_room(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Создатель")
    token = reg["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "code" in data
    assert "id" in data
    assert data["status"] == "waiting"


async def test_list_rooms(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Списочник")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    res = await client.get("/api/rooms")
    assert res.status_code == 200
    assert len(res.json()) >= 1


async def test_get_room(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Получатель")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.get(f"/api/rooms/{code}")
    assert res.status_code == 200
    assert res.json()["code"] == code


async def test_get_room_not_found(client):
    res = await client.get("/api/rooms/ZZZZZZ")
    assert res.status_code == 404


# --- Join/Leave ---


async def test_join_room_as_player(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "ИгрокA")
    reg_b = await register_player(client, "ИгрокB")
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}
    headers_b = {"Authorization": f"Bearer {reg_b['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers_a)
    code = create_res.json()["code"]

    res = await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers_b)
    assert res.status_code == 200
    assert res.json()["team"] == "A"


async def test_join_room_as_observer(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Наблюдатель")
    reg2 = await register_player(client, "Зритель")
    headers = {"Authorization": f"Bearer {reg['token']}"}
    headers2 = {"Authorization": f"Bearer {reg2['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "observer"}, headers=headers2)
    assert res.status_code == 200
    assert res.json()["role"] == "observer"


async def test_join_room_already_in(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Двойник")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers)
    res = await client.post(f"/api/rooms/{code}/join", json={"team": "B", "role": "player"}, headers=headers)
    assert res.status_code == 400
    assert "already" in res.json()["detail"].lower()


async def test_join_room_invalid_team(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Кривой")
    reg2 = await register_player(client, "Кривой2")
    headers = {"Authorization": f"Bearer {reg['token']}"}
    headers2 = {"Authorization": f"Bearer {reg2['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.post(f"/api/rooms/{code}/join", json={"team": "C", "role": "player"}, headers=headers2)
    assert res.status_code == 400


async def test_join_room_invalid_role(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Роль")
    reg2 = await register_player(client, "Роль2")
    headers = {"Authorization": f"Bearer {reg['token']}"}
    headers2 = {"Authorization": f"Bearer {reg2['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "spectator"}, headers=headers2)
    assert res.status_code == 400


async def test_join_room_not_found(client):
    reg = await register_player(client, "Потеряшка")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/rooms/ZZZZZZ/join", json={"team": "A", "role": "player"}, headers=headers)
    assert res.status_code == 404


async def test_join_finished_room(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "ФинА")
    reg_b = await register_player(client, "ФинБ")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])

    # Mark room as finished directly in DB
    from app.database import async_session
    from app.models import Room
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == code))
        room = result.scalar_one_or_none()
        room.status = "finished"
        await db.commit()

    reg_c = await register_player(client, "ФинВ")
    headers_c = {"Authorization": f"Bearer {reg_c['token']}"}
    res = await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers_c)
    assert res.status_code == 400
    assert "closed" in res.json()["detail"].lower()


async def test_leave_room(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "УходА")
    reg_b = await register_player(client, "УходБ")
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}
    headers_b = {"Authorization": f"Bearer {reg_b['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers_a)
    code = create_res.json()["code"]

    await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers_b)

    res = await client.post(f"/api/rooms/{code}/leave", headers=headers_b)
    assert res.status_code == 200
    assert res.json()["ok"] is True


async def test_leave_room_not_found(client):
    reg = await register_player(client, "УходНет")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/rooms/ZZZZZZ/leave", headers=headers)
    assert res.status_code == 404


async def test_join_room_full_team(client):
    """Fill team A to max and verify new player gets rejected."""
    topic_id, _ = await seed_topic()
    players = []
    for i in range(5):
        reg = await register_player(client, f"Full{i}", f"full{i}@test.com")
        players.append(reg)

    headers0 = {"Authorization": f"Bearer {players[0]['token']}"}
    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers0)
    code = create_res.json()["code"]

    # Join 4 players as team A (MAX_PLAYERS_PER_TEAM = 4)
    for i in range(1, 5):
        h = {"Authorization": f"Bearer {players[i]['token']}"}
        await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=h)

    # 5th player should fail
    reg5 = await register_player(client, "Full5", "full5@test.com")
    headers5 = {"Authorization": f"Bearer {reg5['token']}"}
    res = await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers5)
    assert res.status_code == 400
    assert "full" in res.json()["detail"].lower()


# --- Start game ---


async def test_start_room_game(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "СтартА", "start_a@test.com")
    reg_b = await register_player(client, "СтартБ", "start_b@test.com")
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers_a)
    code = create_res.json()["code"]

    await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers_a)
    await client.post(
        f"/api/rooms/{code}/join",
        json={"team": "B", "role": "player"},
        headers={"Authorization": f"Bearer {reg_b['token']}"},
    )

    res = await client.post(f"/api/rooms/{code}/start", json={"topic_id": topic_id}, headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "active"


async def test_start_room_game_no_players_b(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Одинокий", "alone@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers)

    res = await client.post(f"/api/rooms/{code}/start", json={"topic_id": topic_id}, headers=headers)
    assert res.status_code == 400
    assert "team b" in res.json()["detail"].lower()


async def test_start_room_game_topic_not_found(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "ТемаА", "topic_a@test.com")
    reg_b = await register_player(client, "ТемаБ", "topic_b@test.com")
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers_a)
    code = create_res.json()["code"]

    await client.post(f"/api/rooms/{code}/join", json={"team": "A", "role": "player"}, headers=headers_a)
    await client.post(
        f"/api/rooms/{code}/join",
        json={"team": "B", "role": "player"},
        headers={"Authorization": f"Bearer {reg_b['token']}"},
    )

    res = await client.post(f"/api/rooms/{code}/start", json={"topic_id": 9999}, headers=headers_a)
    assert res.status_code == 404


async def test_start_room_game_already_started(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "ПовторА", "repeat_a@test.com")
    reg_b = await register_player(client, "ПовторБ", "repeat_b@test.com")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}

    res = await client.post(f"/api/rooms/{code}/start", json={"topic_id": topic_id}, headers=headers_a)
    assert res.status_code == 400
    assert "waiting" in res.json()["detail"].lower()


async def test_start_room_not_found(client):
    reg = await register_player(client, "НетКомнаты", "nroom@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/rooms/ZZZZZZ/start", json={"topic_id": 1}, headers=headers)
    assert res.status_code == 404


# --- Game flow (next, answer, reset) ---


async def test_room_next_question(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "СледА", "next_a@test.com")
    reg_b = await register_player(client, "СледБ", "next_b@test.com")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}

    res = await client.post(f"/api/rooms/{code}/next", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "active"
    assert res.json()["question_index"] == 0


import pytest


@pytest.mark.skip(reason="POST /answer removed — answers now via WebSocket timer_exp")
async def test_room_submit_answer(client):
    pass


@pytest.mark.skip(reason="POST /answer removed — answers now via WebSocket timer_exp")
async def test_room_submit_answer_wrong(client):
    pass


@pytest.mark.skip(reason="POST /answer removed — answers now via WebSocket timer_exp")
async def test_room_submit_answer_team_duplicate(client):
    pass


@pytest.mark.skip(reason="POST /answer removed — answers now via WebSocket timer_exp")
async def test_room_submit_answer_invalid_option(client):
    pass


@pytest.mark.skip(reason="POST /answer removed — answers now via WebSocket timer_exp")
async def test_room_submit_answer_observer(client):
    pass


@pytest.mark.skip(reason="POST /answer removed — answers now via WebSocket timer_exp")
async def test_room_submit_answer_no_game(client):
    pass


async def test_room_reset(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "СбросА", "reset_a@test.com")
    reg_b = await register_player(client, "СбросБ", "reset_b@test.com")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}

    res = await client.post(f"/api/rooms/{code}/reset", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Room should be gone
    res = await client.get(f"/api/rooms/{code}")
    assert res.status_code == 404


async def test_room_reset_not_found(client):
    reg = await register_player(client, "СбросНет", "reset_no@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    res = await client.post("/api/rooms/ZZZZZZ/reset", headers=headers)
    assert res.status_code == 404


# --- Room state ---


async def test_room_state_waiting(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "Состояние", "state@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.get(f"/api/rooms/{code}/state")
    assert res.status_code == 200
    assert res.json()["status"] == "waiting"


async def test_room_state_active(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "АктивА", "active_a@test.com")
    reg_b = await register_player(client, "АктивБ", "active_b@test.com")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])

    res = await client.get(f"/api/rooms/{code}/state")
    assert res.status_code == 200
    assert res.json()["status"] == "active"


async def test_room_state_not_found(client):
    res = await client.get("/api/rooms/ZZZZZZ/state")
    assert res.status_code == 404


async def test_room_next_question_no_active(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "НетАктив", "noactive@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.post(f"/api/rooms/{code}/next", headers=headers)
    assert res.status_code == 400


async def test_room_finish_game(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "КонецА", "end_a@test.com")
    reg_b = await register_player(client, "КонецБ", "end_b@test.com")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])

    # Mark room as finished directly in DB (game flow is now server-managed via WS)
    from app.database import async_session
    from app.models import Room
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == code))
        room = result.scalar_one_or_none()
        room.status = "finished"
        await db.commit()

    res = await client.get(f"/api/rooms/{code}/state")
    assert res.json()["status"] == "finished"


# --- Nickname editing ---


async def test_update_nickname_in_waiting_room(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "СтарыйНик", "oldnick@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.put(f"/api/rooms/{code}/nickname", json={"nickname": "НовыйНик"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["nickname"] == "НовыйНик"


async def test_update_nickname_in_active_room(client):
    topic_id, _ = await seed_topic()
    reg_a = await register_player(client, "НикАктивА", "nick_active_a@test.com")
    reg_b = await register_player(client, "НикАктивБ", "nick_active_b@test.com")
    code = await create_and_join_room(client, topic_id, reg_a["token"], reg_b["token"])
    headers_a = {"Authorization": f"Bearer {reg_a['token']}"}

    res = await client.put(f"/api/rooms/{code}/nickname", json={"nickname": "Нельзя"}, headers=headers_a)
    assert res.status_code == 400


async def test_update_nickname_empty(client):
    topic_id, _ = await seed_topic()
    reg = await register_player(client, "ПустойНик", "empty_nick@test.com")
    headers = {"Authorization": f"Bearer {reg['token']}"}

    create_res = await client.post("/api/rooms", json={"topic_id": topic_id}, headers=headers)
    code = create_res.json()["code"]

    res = await client.put(f"/api/rooms/{code}/nickname", json={"nickname": ""}, headers=headers)
    assert res.status_code == 400
