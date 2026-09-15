"""Game settings read from DB (SiteSetting) with fallback to config defaults."""

from sqlalchemy import select

from app.config import (
    ANSWER_TIME_SECONDS as _DEFAULT_ANSWER_TIME,
)
from app.config import (
    READING_TIME_SECONDS as _DEFAULT_READING_TIME,
)
from app.config import (
    ROOM_INACTIVITY_TIMEOUT_SECONDS as _DEFAULT_INACTIVITY,
)
from app.database import async_session
from app.models import SiteSetting

_DEFAULTS = {
    "room_inactivity_timeout": _DEFAULT_INACTIVITY,
    "answer_time": _DEFAULT_ANSWER_TIME,
    "reading_time": _DEFAULT_READING_TIME,
}


async def get_setting_int(key: str) -> int:
    default = _DEFAULTS.get(key, 0)
    try:
        async with async_session() as db:
            result = await db.execute(select(SiteSetting).where(SiteSetting.key == key))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return int(setting.value)
    except Exception:
        pass
    return default


async def get_room_inactivity_timeout() -> int:
    return await get_setting_int("room_inactivity_timeout")


async def get_answer_time() -> int:
    return await get_setting_int("answer_time")


async def get_reading_time() -> int:
    return await get_setting_int("reading_time")
