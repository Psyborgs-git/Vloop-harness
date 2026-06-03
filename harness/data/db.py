"""Async SQLAlchemy engine factory — supports SQLite (default) and PostgreSQL.

Usage
─────
    await init_db("sqlite+aiosqlite:///path/to/.vloop/metadata.db")
    # or
    await init_db("postgresql+asyncpg://user:pass@host/dbname")

    factory = get_session_factory()
    async with factory() as session:
        repo = Repository(session)
        ...

    await close_db()
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(db_url: str) -> None:
    """Create tables and initialise the session factory."""
    global _engine, _session_factory

    if db_url.startswith("sqlite"):
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_async_engine(db_url, echo=False, pool_size=5, max_overflow=10)

    _engine = engine
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Create all tables declared in models
    from harness.data import models as _  # noqa: F401 — triggers model registration

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("DB not initialised — call init_db() first")
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-compatible dependency that yields an async session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
