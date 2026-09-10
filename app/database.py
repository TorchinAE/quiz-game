from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migration: add 'name' column to rooms if missing
        result = await conn.execute(text("PRAGMA table_info(rooms)"))
        columns = [row[1] for row in result.fetchall()]
        if "name" not in columns:
            await conn.execute(text("ALTER TABLE rooms ADD COLUMN name VARCHAR(200) NOT NULL DEFAULT ''"))

        # Migration: add 'is_active' column to topics if missing
        result = await conn.execute(text("PRAGMA table_info(topics)"))
        columns = [row[1] for row in result.fetchall()]
        if "is_active" not in columns:
            await conn.execute(text("ALTER TABLE topics ADD COLUMN is_active BOOLEAN DEFAULT 1"))

        # Migration: add 'is_active' column to questions if missing
        result = await conn.execute(text("PRAGMA table_info(questions)"))
        columns = [row[1] for row in result.fetchall()]
        if "is_active" not in columns:
            await conn.execute(text("ALTER TABLE questions ADD COLUMN is_active BOOLEAN DEFAULT 1"))

        # Migration: add 'is_private' column to rooms if missing
        result = await conn.execute(text("PRAGMA table_info(rooms)"))
        columns = [row[1] for row in result.fetchall()]
        if "is_private" not in columns:
            await conn.execute(text("ALTER TABLE rooms ADD COLUMN is_private BOOLEAN DEFAULT 0"))
