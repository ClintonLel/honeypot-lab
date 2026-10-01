"""Lasttest: Budget und Minutengrenze des LLM-Gateways unter parallelen Anfragen.

Viele Anfragen laufen gleichzeitig gegen eine langsame Attrappe. Gezeigt wird
(E-043, method.md V3):

- Das Budget greift. Überschritten wird es höchstens um die Anfragen, die
  gerade laufen, als es erreicht wurde.
- Danach gibt es nur noch 503, und der Anbieter wird nicht mehr gerufen. 429
  entsteht nur an der Minutengrenze (method.md V3).
- Jede Anfrage steht genau einmal in llm_usage.
"""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from app.llm_gateway import Gateway, gateway_of
from tests.cowrie_llm import encode, exec_request
from tests.llm_fakes import NOW, TEST_SECRET, MemoryLedger, Upstream, auth, llm_settings

PATH = "/v1/chat/completions"
# Eine Antwort der Attrappe kostet 1.005 µ€ (siehe test_llm_gateway.py).
COST = 1005
CALLS_IN_BUDGET = 10


@pytest.fixture
def app(monkeypatch):
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", TEST_SECRET)
    monkeypatch.setenv("IP_HMAC_KEY", TEST_SECRET)
    monkeypatch.setenv("INGEST_TOKEN", TEST_SECRET)
    yield create_app()
    get_settings.cache_clear()


def run(app, gateway: Gateway, workers: int, per_worker: int, stagger: float = 0.0):
    """Startet ``workers`` Schleifen mit je ``per_worker`` Anfragen, alle über
    dieselbe App. Gibt die Statuscodes je Schleife zurück."""
    app.dependency_overrides[gateway_of] = lambda: gateway
    body = encode(exec_request("uname -a"))

    async def worker(client: httpx2.AsyncClient, number: int) -> list[int]:
        await asyncio.sleep(number * stagger)
        codes = []
        for _ in range(per_worker):
            response = await client.post(PATH, content=body, headers=auth())
            codes.append(response.status_code)
        return codes

    async def main() -> list[list[int]]:
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://lab-api") as client:
            try:
                return await asyncio.gather(*(worker(client, n) for n in range(workers)))
            finally:
                await gateway.aclose()

    return asyncio.run(main())


def gateway(ledger: MemoryLedger, upstream: Upstream, **overrides) -> Gateway:
    settings = llm_settings(
        llm_budget_day_eur=str(CALLS_IN_BUDGET * COST / 1_000_000),
        llm_calls_per_minute=10_000,
        **overrides,
    )
    return Gateway.from_settings(settings, ledger=ledger, clock=lambda: NOW, transport=upstream.transport)


@pytest.mark.parametrize(("workers", "stagger"), [(8, 0.005), (24, 0.0)])
def test_the_budget_holds_under_parallel_requests(app, workers, stagger):
    ledger = MemoryLedger()
    upstream = Upstream(delay=0.05)
    results = run(app, gateway(ledger, upstream), workers=workers, per_worker=6, stagger=stagger)

    codes = [code for result in results for code in result]
    budget = CALLS_IN_BUDGET * COST
    spent = sum(row.cost_micros for row in ledger.rows)

    # Nur 200 und 503, kein 429: Das gibt es nur an der Minutengrenze.
    assert set(codes) <= {200, 503}
    assert codes.count(200) == upstream.calls == ledger.statuses.count("ok")
    # Das Budget ist erreicht ...
    assert spent >= budget
    # ... und höchstens um die gleichzeitig laufenden Anfragen überschritten.
    assert upstream.peak > 1
    assert spent <= budget + upstream.peak * COST
    assert upstream.calls <= CALLS_IN_BUDGET + upstream.peak - 1
    # Nach dem ersten 503 einer Schleife kommt dort keine 200 mehr.
    for result in results:
        if 503 in result:
            assert 200 not in result[result.index(503):]
    # Jede Anfrage genau eine Zeile.
    assert len(ledger.rows) == len(codes)
    assert ledger.statuses.count("budget_exceeded") == codes.count(503)


def test_after_the_budget_no_request_reaches_the_provider(app):
    ledger = MemoryLedger()
    upstream = Upstream(delay=0.02)
    gw = gateway(ledger, upstream)
    run(app, gw, workers=8, per_worker=4, stagger=0.002)
    calls = upstream.calls

    second = Gateway.from_settings(
        llm_settings(llm_budget_day_eur=str(CALLS_IN_BUDGET * COST / 1_000_000), llm_calls_per_minute=10_000),
        ledger=ledger,
        clock=lambda: NOW,
        transport=upstream.transport,
    )
    results = run(app, second, workers=8, per_worker=5)
    # Ein neuer Prozess liest das Budget aus llm_usage und ruft niemanden mehr.
    assert {code for result in results for code in result} == {503}
    assert upstream.calls == calls


def test_the_minute_limit_holds_under_parallel_requests(app):
    ledger = MemoryLedger()
    upstream = Upstream(delay=0.05)
    gw = Gateway.from_settings(
        llm_settings(llm_calls_per_minute=5), ledger=ledger, clock=lambda: NOW, transport=upstream.transport
    )
    results = run(app, gw, workers=10, per_worker=2)
    codes = [code for result in results for code in result]
    assert codes.count(200) == upstream.calls == 5
    assert codes.count(429) == 15
    assert ledger.statuses.count("rate_limited") == 15
