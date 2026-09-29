"""Gemeinsame Fixtures.

Tests laufen in zwei Stufen:

- ohne Datenbank: überall dort, wo nur Code geprüft wird. Diese Tests laufen
  auf dem Laptop.
- mit Datenbank (Marker ``db``): Migration und Round-Trip gegen ein echtes
  PostgreSQL. Sie laufen im Container auf dem Hauptserver, siehe
  ``server/README.md``. Ohne ``LAB_TEST_DATABASE_URL`` werden sie übersprungen.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SERVER_DIR = Path(__file__).resolve().parents[1]

# Nur für Tests. Echte Secrets stehen ausschließlich in der .env auf dem Server.
TEST_SECRET = "t" * 64


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        postgres_password=TEST_SECRET,
        ip_hmac_key=TEST_SECRET,
        ingest_token=TEST_SECRET,
    )


@pytest.fixture
def app_client(monkeypatch) -> Iterator["TestClient"]:
    """FastAPI-App mit Test-Einstellungen, ohne echte Datenbank.

    Die Werte kommen über ``monkeypatch`` in die Umgebung und verschwinden
    danach wieder. Direkt gesetzte ``os.environ``-Werte blieben stehen und
    würden den Datenbanktests später ein falsches Passwort unterschieben.
    """
    from fastapi.testclient import TestClient

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", TEST_SECRET)
    monkeypatch.setenv("IP_HMAC_KEY", TEST_SECRET)
    monkeypatch.setenv("INGEST_TOKEN", TEST_SECRET)

    from app.main import create_app

    app = create_app()
    # Die Verbindung zur Datenbank ersetzt jeder Test selbst.
    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


@pytest.fixture(scope="session")
def database_url() -> str:
    """Verbindung für die Datenbanktests.

    Entweder vollständig als ``LAB_TEST_DATABASE_URL`` oder nur als Name der
    Testdatenbank in ``LAB_TEST_DATABASE``. Der zweite Weg baut die URL aus den
    üblichen ``POSTGRES_*``-Variablen, damit kein Passwort in der Befehlszeile
    und damit in der Prozessliste steht.
    """
    url = os.environ.get("LAB_TEST_DATABASE_URL", "")
    if url:
        return url

    name = os.environ.get("LAB_TEST_DATABASE", "")
    if name:
        return Settings(environment="test", postgres_db=name).database_url

    pytest.skip("LAB_TEST_DATABASE_URL oder LAB_TEST_DATABASE nicht gesetzt")


def alembic_config(url: str):
    """Alembic-Konfiguration, die auf die Testdatenbank zeigt."""
    from alembic.config import Config

    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "app" / "migrations"))
    # psycopg 3 bedient sync und async, die URL passt für beides.
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def migrated(database_url: str):
    """Fährt das Schema hoch und danach wieder herunter."""
    from alembic import command
    from sqlalchemy import create_engine

    engine = create_engine(database_url, future=True)
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        command.downgrade(config, "base")
        engine.dispose()


@pytest.fixture
def cowrie_events() -> list[dict]:
    """Die echten Beispiel-Ereignisse vom Sensor, Adressen ersetzt."""
    path = FIXTURES / "fixtures.jsonl"
    if not path.exists():
        pytest.skip("fixtures.jsonl fehlt, siehe sensor/README.md")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- App gegen die Testdatenbank ---------------------------------------------

TOKEN = "t" * 64
KEY = "k" * 64


@pytest.fixture
def client(migrated, database_url: str, monkeypatch):
    """Die App, verbunden mit der frisch migrierten Testdatenbank."""
    from fastapi.testclient import TestClient
    from sqlalchemy.engine import make_url

    from app.main import create_app

    url = make_url(database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("POSTGRES_HOST", url.host or "db")
    monkeypatch.setenv("POSTGRES_PORT", str(url.port or 5432))
    monkeypatch.setenv("POSTGRES_USER", url.username or "honeypot")
    monkeypatch.setenv("POSTGRES_PASSWORD", url.password or "")
    monkeypatch.setenv("POSTGRES_DB", url.database or "honeypot_test")
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)
    monkeypatch.setenv("IP_HMAC_KEY", KEY)
    # Ohne MMDB läuft der Ingest weiter, nur ohne Land (Schritt 4.3).
    monkeypatch.setenv("IPINFO_DB_PATH", "/nicht/vorhanden.mmdb")

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def send(client, events, token: str = TOKEN):
    return client.post("/ingest", json=events, headers={"Authorization": f"Bearer {token}"})


# --- Worker-Jobs in Tests ------------------------------------------------------


def make_ctx(database_url: str, now):
    """Kontext für einen Worker-Job gegen die Testdatenbank, mit fester Uhr."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from worker import jobs

    # NullPool: Jeder Aufruf läuft in einer eigenen Ereignisschleife, gepoolte
    # Verbindungen dürfen nicht hinüberwandern.
    engine = create_async_engine(database_url, poolclass=NullPool)
    return jobs.Context(settings=Settings(environment="test"), engine=engine, now=lambda: now)


def run(coro_fn, ctx, **kwargs):
    """Führt einen Job synchron aus und gibt die Verbindungen danach frei."""
    import asyncio

    async def call():
        try:
            return await coro_fn(ctx, **kwargs)
        finally:
            await ctx.engine.dispose()

    return asyncio.run(call())
