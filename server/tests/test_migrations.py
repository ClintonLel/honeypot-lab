"""Migration gegen eine echte Datenbank.

Diese Tests brauchen PostgreSQL und laufen deshalb im Container auf dem
Hauptserver (siehe ``server/README.md``):

    docker compose -f docker-compose.server.yml run --rm \\
        -e LAB_TEST_DATABASE_URL=postgresql+psycopg://honeypot:...@db:5432/honeypot_test \\
        api pytest

Ohne ``LAB_TEST_DATABASE_URL`` überspringt pytest sie.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select

from app.models import Base, Session

pytestmark = pytest.mark.db

SERVER_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "app" / "migrations"))
    # psycopg 3 bedient sync und async, die URL passt für beides.
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def migrated(database_url: str):
    """Fährt das Schema hoch und danach wieder herunter."""
    engine = create_engine(database_url, future=True)
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        command.downgrade(config, "base")
        engine.dispose()


def test_migration_matches_the_models(migrated):
    """``alembic check`` von Hand: nach der Migration darf es keinen Unterschied geben."""
    with migrated.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        differences = compare_metadata(context, Base.metadata)
    assert differences == [], f"Schema und Modelle laufen auseinander: {differences}"


def test_downgrade_removes_every_table(database_url: str):
    engine = create_engine(database_url, future=True)
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    remaining = set(Base.metadata.tables) & set(inspect(engine).get_table_names())
    engine.dispose()
    assert remaining == set()


def test_a_session_round_trip_keeps_only_the_hash(migrated):
    from sqlalchemy.orm import Session as OrmSession

    started = datetime(2026, 9, 17, 14, 26, 31, tzinfo=timezone.utc)
    with OrmSession(migrated) as db:
        db.add(
            Session(
                cowrie_session="0123456789ab",
                variant="a",
                sensor_name="hp-a",
                ip_hash="f" * 64,
                country="DE",
                asn="AS64496",
                as_name="Beispiel AS",
                started_at=started,
            )
        )
        db.commit()

        stored = db.scalar(select(Session).where(Session.cowrie_session == "0123456789ab"))
        assert stored is not None
        assert stored.ip_hash == "f" * 64
        assert stored.command_count == 0
        assert stored.interactive is None
        assert stored.started_at == started


def test_variant_check_rejects_unknown_values(migrated):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session as OrmSession

    with OrmSession(migrated) as db:
        db.add(
            Session(
                cowrie_session="ffffffffffff",
                variant="x",
                sensor_name="hp-x",
                ip_hash="a" * 64,
                started_at=datetime.now(tz=timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
