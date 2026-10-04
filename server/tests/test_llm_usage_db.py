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

from app.llm_check import gateway_counts
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
        model="gemini-3.1-flash-lite",
        status="ok",
        prompt_tokens=8000,
        completion_tokens=320,
        total_tokens=8320,
        cached_tokens=7424,
        reasoning_tokens=300,
        cost_micros=810,
        latency_ms=812,
        refusal=True,
    )

    async def action(ledger):
        await ledger.record(entry)

    with_ledger(database_url, action)
    [row] = rows(migrated)
    assert (row.status, row.model, row.cached_tokens, row.reasoning_tokens, row.cost_micros, row.latency_ms) == (
        "ok",
        "gemini-3.1-flash-lite",
        7424,
        300,
        810,
        812,
    )
    assert row.refusal is True
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
    assert stored[0].cost_micros == 360
    assert (stored[0].reasoning_tokens, stored[0].refusal) == (0, False)
    assert (stored[1].reasoning_tokens, stored[1].refusal) == (0, False)
    assert GATEWAY_TOKEN not in str([r.__dict__ for r in stored])


# --- python -m app.llm_check: Sicht des Gateways (E-045) --------------------------


def test_llm_check_counts_statuses_refusals_cache_and_costs(migrated, database_url):
    entries = [
        UsageRecord(NOW, "g", "ok", prompt_tokens=8000, cached_tokens=6000, cost_micros=700_000, latency_ms=900, refusal=True),
        UsageRecord(NOW, "g", "ok", prompt_tokens=8000, cached_tokens=6000, cost_micros=300_000, latency_ms=800),
        UsageRecord(NOW, "g", "upstream_blocked", prompt_tokens=4000, cost_micros=0, latency_ms=700),
        UsageRecord(NOW, "g", "local_empty"),
        UsageRecord(NOW, "g", "rate_limited"),
    ]

    async def action(ledger):
        for entry in entries:
            await ledger.record(entry)

    with_ledger(database_url, action)
    with migrated.connect() as connection:
        result = gateway_counts(connection, NOW.replace(hour=0), NOW, days=2)
    assert result == {
        "status": {"local_empty": 1, "ok": 2, "rate_limited": 1, "upstream_blocked": 1},
        "weigerungen": 1,
        # 12.000 von 20.000 Eingabe-Tokens aus dem Cache.
        "cache_quote": 0.6,
        "kosten_usd": 1.0,
        "tage": 2,
        # Drei Aufrufe beim Anbieter in zwei Tagen.
        "aufrufe_je_tag": 1.5,
        # 1 $ in 2 Tagen → 15,20 $ in 30,4 Tagen.
        "kosten_je_monat_usd": 15.2,
    }


def test_without_a_period_llm_check_counts_from_the_first_row(migrated, database_url):
    async def action(ledger):
        await ledger.record(UsageRecord(NOW, "g", "ok", prompt_tokens=10, cost_micros=304_000, latency_ms=1))

    with_ledger(database_url, action)
    with migrated.connect() as connection:
        result = gateway_counts(connection, datetime(2020, 1, 1, tzinfo=timezone.utc), NOW.replace(day=18))
    assert result["tage"] == 4
    assert result["kosten_je_monat_usd"] == 2.31
    assert result["cache_quote"] == 0.0
