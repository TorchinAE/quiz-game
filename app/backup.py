"""Backup system: archive images + CSV + DB, upload to external server."""

import asyncio
import logging
import os
from datetime import datetime

from app.config import (
    BACKUP_INTERVAL_DAYS,
    BACKUP_SERVER_HOST,
    BACKUP_SERVER_KEY,
    BACKUP_SERVER_PATH,
    BACKUP_SERVER_USER,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
BACKUP_DIR = "/tmp/quiz_backup"


async def create_backup() -> str:
    """Create a backup archive. Returns path to archive."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"quiz_backup_{timestamp}.tar.gz"
    archive_path = os.path.join(BACKUP_DIR, archive_name)

    sources = []
    pictures = os.path.join(PROJECT_ROOT, "pictures")
    if os.path.isdir(pictures):
        sources.append("pictures")
    csv_path = os.path.join(PROJECT_ROOT, "data", "questions.csv")
    if os.path.isfile(csv_path):
        sources.append("data/questions.csv")
    db_path = os.path.join(PROJECT_ROOT, "data", "quiz.db")
    if os.path.isfile(db_path):
        sources.append("data/quiz.db")

    if not sources:
        raise RuntimeError("Nothing to backup")

    proc = await asyncio.create_subprocess_exec(
        "tar", "-czf", archive_path, "-C", PROJECT_ROOT, *sources,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("tar failed")

    logger.info("Backup created: %s", archive_path)
    return archive_path


async def upload_backup(archive_path: str) -> bool:
    """Upload backup to external server via SCP. Returns True on success."""
    if not BACKUP_SERVER_HOST or not BACKUP_SERVER_USER:
        logger.info("Backup upload skipped (no server configured)")
        return False

    scp_args = ["scp"]
    if BACKUP_SERVER_KEY:
        scp_args += ["-i", BACKUP_SERVER_KEY]
    scp_args += [
        archive_path,
        f"{BACKUP_SERVER_USER}@{BACKUP_SERVER_HOST}:{BACKUP_SERVER_PATH}",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *scp_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        if proc.returncode == 0:
            logger.info("Backup uploaded to %s", BACKUP_SERVER_HOST)
            return True
        logger.warning("SCP failed with code %d", proc.returncode)
        return False
    except Exception:
        logger.exception("Backup upload failed")
        return False


async def auto_backup_loop():
    """Background task that runs backup every N days."""
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_DAYS * 86400)
        try:
            path = await create_backup()
            await upload_backup(path)
            from app.telegram_bot import notify_backup_complete

            await notify_backup_complete()
        except Exception:
            logger.exception("Auto backup failed")
