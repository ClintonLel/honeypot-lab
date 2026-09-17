"""Zugang zur Datenbank.

Asynchron über SQLAlchemy 2 und psycopg 3. Die Verbindung geht ausschließlich
über das interne Docker-Netz ``lab_internal``; PostgreSQL veröffentlicht keinen
Port auf dem Host (E-020).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

# max_connections steht auf 40. API und Worker teilen sich das, deshalb hier
# kleine Pools statt der Standardwerte.
POOL_SIZE = 5
MAX_OVERFLOW = 5


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        # Nach einem Neustart der Datenbank sind Verbindungen im Pool tot.
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Eine Sitzung je Anfrage, Rollback bei Fehlern."""
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
