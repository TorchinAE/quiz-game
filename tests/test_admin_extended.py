import pytest

pytestmark = pytest.mark.asyncio


async def test_toggle_topic_active(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post("/api/admin/topics", json={"name": "Toggle Topic"}, headers=headers)
    topic_id = res.json()["id"]

    # Toggle off
    res = await client.put(f"/api/admin/topics/{topic_id}/toggle", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Toggle back on
    res = await client.put(f"/api/admin/topics/{topic_id}/toggle", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is True


async def test_toggle_question_active(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    topic_res = await client.post("/api/admin/topics", json={"name": "Q Toggle Topic"}, headers=headers)
    topic_id = topic_res.json()["id"]

    q_data = {
        "topic_id": topic_id,
        "text": "Toggle question?",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "A",
    }
    res = await client.post("/api/admin/questions", json=q_data, headers=headers)
    q_id = res.json()["id"]

    # Toggle off
    res = await client.put(f"/api/admin/questions/{q_id}/toggle", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Toggle back on
    res = await client.put(f"/api/admin/questions/{q_id}/toggle", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is True


async def test_toggle_topic_not_found(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.put("/api/admin/topics/9999/toggle", headers=headers)
    assert res.status_code == 404


async def test_toggle_question_not_found(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.put("/api/admin/questions/9999/toggle", headers=headers)
    assert res.status_code == 404


async def test_toggle_no_auth(client):
    res = await client.put("/api/admin/topics/1/toggle")
    assert res.status_code == 403


async def test_list_images(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/admin/images", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_list_images_no_auth(client):
    res = await client.get("/api/admin/images")
    assert res.status_code == 403


async def test_delete_image_not_found(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.delete("/api/admin/images/nonexistent.png", headers=headers)
    assert res.status_code == 404


async def test_stats_endpoint(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/admin/stats", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_visits" in data
    assert "unique_players" in data
    assert "total_rooms" in data
    assert "active_rooms" in data
    assert "total_players" in data
    assert "total_games_finished" in data


async def test_stats_visits_endpoint(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/admin/stats/visits?days=30", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_stats_games_endpoint(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/admin/stats/games?days=30", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_stats_no_auth(client):
    res = await client.get("/api/admin/stats")
    assert res.status_code == 403


async def test_backup_trigger_no_auth(client):
    res = await client.post("/api/admin/backup")
    assert res.status_code == 403


async def test_backup_download_no_auth(client):
    res = await client.get("/api/admin/backup/download")
    assert res.status_code == 403


async def test_backup_download_no_archives(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/admin/backup/download", headers=headers)
    assert res.status_code == 404
