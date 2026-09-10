import os
import pytest
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.asyncio


async def test_trigger_backup_no_auth(client):
    res = await client.post("/api/admin/backup")
    assert res.status_code == 403


async def test_trigger_backup_as_admin(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    with (
        patch("app.backup.create_backup", new_callable=AsyncMock, return_value="/tmp/quiz_backup/test.tar.gz"),
        patch("app.backup.upload_backup", new_callable=AsyncMock, return_value=False),
    ):
        res = await client.post("/api/admin/backup", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "path" in data


async def test_backup_download_no_archives(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/admin/backup/download", headers=headers)
    assert res.status_code == 404


async def test_backup_download_with_archive(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    backup_dir = "/tmp/quiz_backup"
    os.makedirs(backup_dir, exist_ok=True)
    test_archive = os.path.join(backup_dir, "quiz_backup_20260101_120000.tar.gz")
    try:
        with open(test_archive, "wb") as f:
            f.write(b"\x1f\x8b\x08\x00fake-gz-data")
        res = await client.get("/api/admin/backup/download", headers=headers)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/gzip"
    finally:
        if os.path.exists(test_archive):
            os.remove(test_archive)


async def test_backup_download_no_auth(client):
    res = await client.get("/api/admin/backup/download")
    assert res.status_code == 403
