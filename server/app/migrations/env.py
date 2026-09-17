"""Alembic-Umgebung.

Die Verbindung kommt aus den Einstellungen, also aus Umgebungsvariablen. Für
einen Trockenlauf ohne Datenbank lässt sich die URL überschreiben:

    alembic -x url=postgresql+psycopg://u:p@localhost/db upgrade head --sql
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import Connection

# Bei "alembic" aus server/ liegt das Paket app neben alembic.ini.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """URL in dieser Reihenfolge: -x url=…, alembic.ini, Umgebungsvariablen."""
    override = context.get_x_argument(as_dictionary=True).get("url")
    configured = override or config.get_main_option("sqlalchemy.url")
    if not configured:
        from app.config import get_settings

        configured = get_settings().database_url
    # psycopg 3 kann synchron und asynchron. Ohne Treiber im Schema würde
    # SQLAlchemy psycopg2 nehmen, das hier nicht installiert ist.
    if configured.startswith("postgresql://"):
        configured = configured.replace("postgresql://", "postgresql+psycopg://", 1)
    return configured


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    # Eigene Verbindung statt des Anwendungs-Pools: Migrationen laufen einmal.
    engine = create_async_engine(database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
