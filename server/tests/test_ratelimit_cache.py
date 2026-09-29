"""Prüft Rate-Limit, Client-Erkennung und den Statistik-Cache (ohne Datenbank)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.ratelimit import RateLimiter, client_key
from app.stats import TTLCache, breakdown_table, heatmap_matrix, pivot_countries, recent_messages


def request_from(forwarded: str | None = None, host: str = "172.20.0.5"):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


# --- Client-Erkennung -------------------------------------------------------


def test_the_key_is_not_the_address():
    key = client_key(request_from("203.0.113.9"))
    assert "203.0.113.9" not in key
    assert len(key) == 32


def test_the_first_forwarded_address_counts():
    """Caddy setzt X-Forwarded-For selbst, der erste Eintrag ist der Besucher."""
    assert client_key(request_from("203.0.113.9, 172.20.0.5")) == client_key(request_from("203.0.113.9"))


def test_different_visitors_get_different_keys():
    assert client_key(request_from("203.0.113.9")) != client_key(request_from("203.0.113.10"))


def test_without_the_header_the_connection_counts():
    assert client_key(request_from(None, host="172.20.0.5")) == client_key(request_from("172.20.0.5"))


# --- Token-Bucket -----------------------------------------------------------


def test_sixty_requests_pass_the_sixty_first_waits():
    limiter = RateLimiter(per_minute=60)
    assert all(limiter.allow("k", now=0.0) == 0 for _ in range(60))
    wait = limiter.allow("k", now=0.0)
    assert 0 < wait <= 1.0


def test_the_bucket_refills_over_time():
    limiter = RateLimiter(per_minute=60)
    for _ in range(60):
        limiter.allow("k", now=0.0)
    assert limiter.allow("k", now=0.5) > 0
    assert limiter.allow("k", now=1.5) == 0


def test_clients_do_not_share_a_bucket():
    limiter = RateLimiter(per_minute=1)
    assert limiter.allow("a", now=0.0) == 0
    assert limiter.allow("b", now=0.0) == 0
    assert limiter.allow("a", now=0.0) > 0


def test_the_number_of_remembered_clients_is_bounded():
    limiter = RateLimiter(max_keys=3)
    for key in "abcde":
        limiter.allow(key, now=0.0)
    assert limiter.known_keys == ["c", "d", "e"]


def test_streams_are_counted_and_released():
    limiter = RateLimiter(streams_per_client=2)
    assert limiter.acquire_stream("k") and limiter.acquire_stream("k")
    assert not limiter.acquire_stream("k")
    limiter.release_stream("k")
    assert limiter.acquire_stream("k")


def test_the_statistics_answer_429_with_retry_after(app_client):
    limiter = app_client.app.state.limiter
    limiter.per_minute = 1
    key = client_key(request_from("198.51.100.99"))
    limiter.allow(key)
    response = app_client.get("/stats/overview", headers={"X-Forwarded-For": "198.51.100.99"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


# --- Cache ------------------------------------------------------------------


def test_the_cache_computes_once_within_its_lifetime():
    cache = TTLCache(ttl=30)
    calls = []

    async def compute():
        calls.append(1)
        return {"n": len(calls)}

    async def run():
        first = await cache.get("k", compute)
        second = await cache.get("k", compute)
        return first, second

    assert asyncio.run(run()) == ({"n": 1}, {"n": 1})
    assert len(calls) == 1


def test_parallel_requests_compute_only_once():
    cache = TTLCache(ttl=30)
    calls = []

    async def compute():
        calls.append(1)
        await asyncio.sleep(0.01)
        return len(calls)

    async def run():
        return await asyncio.gather(*(cache.get("k", compute) for _ in range(10)))

    assert asyncio.run(run()) == [1] * 10
    assert len(calls) == 1


def test_an_expired_entry_is_computed_again():
    cache = TTLCache(ttl=0)
    calls = []

    async def compute():
        calls.append(1)
        return len(calls)

    async def run():
        return [await cache.get("k", compute), await cache.get("k", compute)]

    assert asyncio.run(run()) == [1, 2]


def test_the_cache_is_bounded():
    cache = TTLCache(ttl=30, max_entries=2)

    async def compute():
        return 1

    async def run():
        for key in "abc":
            await cache.get(key, compute)

    asyncio.run(run())
    assert list(cache._entries) == ["b", "c"]


# --- Umformungen ------------------------------------------------------------


def test_countries_are_sorted_by_total():
    rows = [("DE", "a", 3), ("DE", "all", 3), ("CN", "a", 5), ("CN", "b", 2), ("CN", "all", 7)]
    assert pivot_countries(rows) == [
        {"country": "CN", "a": 5, "b": 2, "all": 7},
        {"country": "DE", "a": 3, "b": 0, "all": 3},
    ]


def test_countries_are_capped():
    rows = [(f"C{i}", "all", i) for i in range(60)]
    assert len(pivot_countries(rows, limit=50)) == 50


def test_the_heatmap_puts_monday_first():
    matrix = heatmap_matrix([(1, "00", 4), (7, "23", 2)])
    assert len(matrix) == 7 and all(len(row) == 24 for row in matrix)
    assert matrix[0][0] == 4
    assert matrix[6][23] == 2


def test_the_breakdown_derives_sessions_without_commands():
    rows = [("a", "sessions", 10), ("a", "sessions_interactive", 2), ("a", "sessions_exec", 3)]
    table = breakdown_table(rows)
    assert table["a"] == {"sessions": 10, "interactive": 2, "exec": 3, "without_commands": 5}
    assert table["b"]["sessions"] == 0


def test_recent_commands_come_oldest_first_and_short():
    newer = (datetime(2026, 9, 18, 12, 1, tzinfo=timezone.utc), "a", "NL", "x" * 200, [])
    older = (datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc), "b", None, "uname -a", ["T1082"])
    messages = recent_messages([newer, older])
    assert messages[0] == {
        "ts": "2026-09-18T12:00:00Z",
        "variant": "b",
        "country": None,
        "event": "command",
        "command": "uname -a",
        "techniques": ["T1082"],
    }
    assert len(messages[1]["command"]) == 80 and messages[1]["command"].endswith("…")
    assert messages[1]["techniques"] == []
