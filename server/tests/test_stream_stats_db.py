"""Stream und Statistik gegen eine echte Datenbank (Marker ``db``).

Die echten Beispiel-Ereignisse vom Sensor laufen über die API ein. Geprüft
wird, was im Stream ankommt, und was die Statistik-Endpunkte daraus machen.
Die Erwartungen werden aus den Fixtures abgeleitet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.stats import RECENT_COMMANDS
from app.stream import STREAM_EVENTS, Broadcaster
from tests.conftest import make_ctx, run, send
from worker import jobs

pytestmark = pytest.mark.db

# „Heute“ ist in diesen Tests der Tag der Beispieldaten.
TODAY_EVENING = datetime(2026, 9, 17, 23, 0, tzinfo=timezone.utc)


def drain(queue) -> list[dict]:
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    return messages


# --- Stream -----------------------------------------------------------------


@pytest.fixture
def listener(client):
    # Groß genug für alle Beispielereignisse, sonst fielen die ältesten raus.
    client.app.state.broadcaster = Broadcaster(queue_size=1000)
    return client.app.state.broadcaster.subscribe()


def test_every_stored_event_of_interest_reaches_the_stream(client, listener, cowrie_events):
    body = send(client, cowrie_events).json()
    messages = drain(listener)
    expected = sum(1 for e in cowrie_events if e["eventid"] in STREAM_EVENTS)
    assert len(messages) == expected
    assert body["accepted"] == len(cowrie_events)


def test_the_stream_carries_no_address_of_a_participant(client, listener, cowrie_events):
    send(client, cowrie_events)
    everything = json.dumps(drain(listener))
    addresses = {e[field] for e in cowrie_events for field in ("src_ip", "dst_ip") if e.get(field)}
    for address in addresses:
        assert address not in everything
        assert address.replace(".", "[.]") not in everything


def test_command_previews_are_short(client, listener, cowrie_events):
    send(client, cowrie_events)
    commands = [m["command"] for m in drain(listener) if m["event"] == "command"]
    assert commands
    assert all(len(command) <= 80 for command in commands)


def test_duplicates_are_not_streamed_again(client, listener, cowrie_events):
    send(client, cowrie_events)
    drain(listener)
    send(client, cowrie_events)
    assert drain(listener) == []


def test_messages_arrive_in_the_order_of_the_batch(client, listener, cowrie_events):
    send(client, cowrie_events)
    stamps = [m["ts"] for m in drain(listener)]
    assert stamps == sorted(stamps)


# --- Statistik --------------------------------------------------------------


@pytest.fixture
def aggregated(client, cowrie_events, database_url):
    send(client, cowrie_events)
    run(jobs.aggregate_daily_stats, make_ctx(database_url, TODAY_EVENING))
    client.app.state.clock = lambda: TODAY_EVENING
    return cowrie_events


def get(client, path: str, **params):
    response = client.get(path, params=params, headers={"X-Forwarded-For": "198.51.100.200"})
    assert response.status_code == 200, response.text
    return response


def test_the_overview_counts_today_and_in_total(client, aggregated):
    sessions = len({e["session"] for e in aggregated})
    logins = len({e["session"] for e in aggregated if e["eventid"] == "cowrie.login.success"})
    commands = sum(1 for e in aggregated if e["eventid"] == "cowrie.command.input")

    body = get(client, "/stats/overview").json()
    assert body["today"]["a"] == {"sessions": sessions, "logins": logins, "commands": commands}
    assert body["today"]["all"] == body["today"]["a"]
    assert body["today"]["b"] == {"sessions": 0, "logins": 0, "commands": 0}
    # Vor dem 17.09. gibt es nichts, gesamt ist also gleich heute.
    assert body["total"]["a"] == body["today"]["a"]
    assert body["total"]["since"] == "2026-09-17"
    assert isinstance(body["sensor"]["online"], bool)


def test_countries_list_unknown_origins(client, aggregated):
    body = get(client, "/stats/countries", days=7).json()
    sessions = len({e["session"] for e in aggregated})
    # Ohne IPinfo-Datenbank im Test hat keine Sitzung ein Land.
    assert body["countries"] == [{"country": "??", "a": sessions, "b": 0, "all": sessions}]
    assert body["until"] == "2026-09-17"


def test_the_heatmap_adds_up_to_the_sessions(client, aggregated):
    body = get(client, "/stats/heatmap", days=7).json()
    assert len(body["values"]) == 7 and all(len(row) == 24 for row in body["values"])
    assert sum(map(sum, body["values"])) == len({e["session"] for e in aggregated})
    # Der 17.09.2026 ist ein Donnerstag.
    assert sum(body["values"][3]) == sum(map(sum, body["values"]))
    assert body["max"] == max(map(max, body["values"]))


def test_the_breakdown_matches_the_sessions(client, aggregated):
    with_pty = {e["session"] for e in aggregated if e["eventid"] == "cowrie.client.size"}
    with_commands = {e["session"] for e in aggregated if e["eventid"] == "cowrie.command.input"}
    sessions = {e["session"] for e in aggregated}

    body = get(client, "/stats/breakdown").json()
    assert body["variants"]["a"] == {
        "sessions": len(sessions),
        "interactive": len(with_pty),
        "exec": len(with_commands - with_pty),
        "without_commands": len(sessions - with_commands),
    }


def test_there_are_no_campaigns_yet(client, aggregated):
    assert get(client, "/stats/campaigns").json() == {"campaigns": []}


def test_the_recent_commands_are_the_last_ones_of_the_stream(client, listener, cowrie_events):
    send(client, cowrie_events)
    streamed = [m for m in drain(listener) if m["event"] == "command"]

    body = get(client, "/stats/recent").json()
    assert body["messages"] == streamed[-RECENT_COMMANDS:]


def test_the_recent_commands_carry_no_address(client, cowrie_events):
    send(client, cowrie_events)
    everything = json.dumps(get(client, "/stats/recent").json())
    addresses = {e[field] for e in cowrie_events for field in ("src_ip", "dst_ip") if e.get(field)}
    for address in addresses:
        assert address not in everything
        assert address.replace(".", "[.]") not in everything


def test_without_commands_the_list_is_empty(client):
    assert get(client, "/stats/recent").json() == {"messages": []}


def test_statistics_may_be_cached_for_30_seconds(client, aggregated):
    for path in (
        "/stats/overview",
        "/stats/countries",
        "/stats/heatmap",
        "/stats/breakdown",
        "/stats/campaigns",
        "/stats/recent",
    ):
        assert get(client, path).headers["Cache-Control"] == "public, max-age=30"


def test_a_repeated_request_comes_from_the_cache(client, aggregated, cowrie_events):
    first = get(client, "/stats/overview").json()
    later = dict(cowrie_events[0], session="neue0sitzung", timestamp="2026-09-17T20:00:00.000000Z")
    send(client, [later])
    assert get(client, "/stats/overview").json() == first
    client.app.state.stats_cache._entries.clear()
    assert get(client, "/stats/overview").json()["today"]["a"]["sessions"] == first["today"]["a"]["sessions"] + 1


@pytest.mark.parametrize(
    "path, params",
    [
        ("/stats/countries", {"days": 0}),
        ("/stats/countries", {"days": 366}),
        ("/stats/heatmap", {"variant": "x"}),
        ("/stats/breakdown", {"days": "viele"}),
    ],
)
def test_impossible_parameters_are_refused(client, path, params):
    response = client.get(path, params=params, headers={"X-Forwarded-For": "198.51.100.201"})
    assert response.status_code == 422
