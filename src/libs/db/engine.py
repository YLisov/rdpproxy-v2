from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.loader import DatabaseConfig


def create_engine(cfg: DatabaseConfig) -> AsyncEngine:
    """Create an async SQLAlchemy engine from config."""
    return create_async_engine(
        cfg.url,
        pool_pre_ping=True,
        pool_size=cfg.pool_size,
        max_overflow=cfg.max_overflow,
        echo=cfg.echo,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False, autocommit=False)


def build_session_factory(cfg: DatabaseConfig) -> async_sessionmaker[AsyncSession]:
    """Convenience: create engine + sessionmaker in one call."""
    return create_sessionmaker(create_engine(cfg))


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around a series of operations."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
