"""llm_usage gegen eine echte Datenbank (Marker ``db``, Schritt 7.2).

Läuft in der CI und im Container auf dem Hauptserver, siehe
``server/README.md``. Der Anbieter ist auch hier eine Attrappe.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.llm_gateway import DbLedger, Gateway, UsageRecord, gateway_of
from app.models import LlmUsage
from tests.conftest import TOKEN
from tests.cowrie_llm import encode, exec_request
from tests.llm_fakes import GATEWAY_TOKEN, NOW, Upstream, auth, llm_settings

pytestmark = pytest.mark.db


def with_ledger(database_url: str, action):
    async def main():
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await action(DbLedger(async_sessionmaker(engine, expire_on_commit=False)))
        finally:
            await engine.dispose()

    return asyncio.run(main())


def rows(engine) -> list[LlmUsage]:
    from sqlalchemy.orm import Session as OrmSession

    with OrmSession(engine) as db:
        return list(db.scalars(select(LlmUsage).order_by(LlmUsage.id)))


def test_a_record_is_stored_with_cached_tokens(migrated, database_url):
    entry = UsageRecord(
        occurred_at=NOW,
        model="test-model-mini",
        status="ok",
        prompt_tokens=8000,
        completion_tokens=20,
        total_tokens=8020,
        cached_tokens=7424,
        cost_micros=1005,
        latency_ms=812,
    )

    async def action(ledger):
        await ledger.record(entry)

    with_ledger(database_url, action)
    [row] = rows(migrated)
    assert (row.status, row.model, row.cached_tokens, row.cost_micros, row.latency_ms) == (
        "ok",
        "test-model-mini",
        7424,
        1005,
        812,
    )
    assert row.session_id is None
    assert row.occurred_at == NOW


def test_spent_sums_the_month_and_the_day(migrated, database_url):
    def at(day: int, month: int = 10) -> datetime:
        return datetime(2026, month, day, 8, 0, tzinfo=timezone.utc)

    entries = [
        UsageRecord(at(30, 9), "m", "ok", cost_micros=5_000),  # Vormonat
        UsageRecord(at(1), "m", "ok", cost_micros=300),
        UsageRecord(at(13), "m", "timeout", cost_micros=40),
        UsageRecord(at(14), "m", "ok", cost_micros=7),
        UsageRecord(at(14), "m", "rejected"),
    ]

    async def action(ledger):
        for entry in entries:
            await ledger.record(entry)
        return await ledger.spent(
            datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 14, tzinfo=timezone.utc)
        )

    assert with_ledger(database_url, action) == (347, 7)


def test_spent_is_zero_without_rows(migrated, database_url):
    async def action(ledger):
        return await ledger.spent(NOW, NOW)

    assert with_ledger(database_url, action) == (0, 0)


def test_the_gateway_writes_one_row_per_request(client, migrated):
    upstream = Upstream()
    gateway = Gateway.from_settings(
        llm_settings(),
        ledger=DbLedger(client.app.state.session_factory),
        clock=lambda: NOW,
        transport=upstream.transport,
    )
    client.app.dependency_overrides[gateway_of] = lambda: gateway
    try:
        ok = client.post("/v1/chat/completions", content=encode(exec_request("id")), headers=auth())
        bad = client.post("/v1/chat/completions", content=b"{}", headers=auth())
        unauthorized = client.post("/v1/chat/completions", content=b"{}", headers=auth(TOKEN))
    finally:
        client.portal.call(gateway.aclose)

    assert (ok.status_code, bad.status_code, unauthorized.status_code) == (200, 400, 401)
    stored = rows(migrated)
    assert [r.status for r in stored] == ["ok", "rejected"]
    assert stored[0].cached_tokens == 7424
    assert stored[0].cost_micros == 1005
    assert GATEWAY_TOKEN not in str([r.__dict__ for r in stored])
