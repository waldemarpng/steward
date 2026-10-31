"""Engine, sessions, and table creation."""

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from steward.db.models import Base
from steward.settings import get_settings


def make_engine(url: str | None = None) -> AsyncEngine:
    """Async engine. Creates the SQLite parent directory and turns on foreign keys."""
    database_url = _as_async_url(url or get_settings().database_url)
    _ensure_sqlite_parent(database_url)
    engine = create_async_engine(database_url)
    if database_url.startswith("sqlite"):
        event.listen(engine.sync_engine, "connect", enable_sqlite_foreign_keys)
    return engine


async def create_tables(engine: AsyncEngine) -> None:
    """Create any missing tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def make_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    """Session factory that keeps loaded objects after commit."""
    return async_sessionmaker(bind=engine or make_engine(), expire_on_commit=False)


def enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Turn on foreign keys for one SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _as_async_url(database_url: str) -> str:
    if database_url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + database_url.removeprefix("sqlite://")
    return database_url


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    path = database_url.removeprefix(prefix)
    if path in ("", ":memory:"):
        return
    parent = Path(path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
