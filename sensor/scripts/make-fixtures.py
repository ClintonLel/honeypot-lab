#!/usr/bin/env python3
"""Beispiel-Logs für ``server/tests/fixtures`` erzeugen.

Läuft auf dem Sensor, liest ``cowrie.json`` und schreibt ausgewählte, jeweils
vollständige Sitzungen als JSON Lines heraus. Dabei wird jede Adresse der
Beteiligten ersetzt:

- Quell-IPs der Angreifer (``src_ip``) durch ``203.0.113.x`` beziehungsweise
  ``2001:db8::x``
- die Adresse des Sensors (``dst_ip``) durch ``198.51.100.1``

Private und Loopback-Adressen bleiben unverändert: Sie gehören niemandem
außerhalb des Sensors, und an ``127.0.0.1`` sind später unsere eigenen
Testsitzungen zu erkennen (Schritt 7.1).

Ersetzt wird nicht nur das Feld, sondern jedes Vorkommen dieser Adressen in
allen Werten, also auch in ``message`` oder in einem Befehl, den ein Angreifer
mit seiner eigenen Adresse abgesetzt hat. Auf dem Laptop landet damit keine
echte Adresse eines Beteiligten (E-009).

Adressen und URLs *innerhalb* der Angreifer-Befehle bleiben stehen, solange sie
nicht zu den Beteiligten gehören: Sie sind Gegenstand der Untersuchung, und die
Tests für die Entschärfung (hxxp, [.]) brauchen echtes Material. Das Repo ist
privat; für die öffentliche Anzeige entschärft die API später ohnehin.

Aufruf auf dem Sensor:

    sudo python3 /opt/honeypot-lab/sensor/scripts/make-fixtures.py > /tmp/fixtures.jsonl

Die Zusammenfassung geht nach stderr und enthält nur Zahlen, nie eine Adresse.
"""

from __future__ import annotations

import argparse
import glob
import ipaddress
import json
import sys
from collections import Counter, defaultdict
from typing import Any, Iterable

DEFAULT_LOGS = "/srv/honeypot/a/var/log/cowrie/cowrie.json*"

# Dokumentationsbereiche laut RFC 5737 und RFC 3849.
ATTACKER_V4 = ipaddress.ip_address("203.0.113.1")
ATTACKER_V6 = ipaddress.ip_address("2001:db8::1")
SENSOR_V4 = "198.51.100.1"
SENSOR_V6 = "2001:db8:ffff::1"

# Felder, in denen eine Adresse eines Beteiligten steht.
SOURCE_FIELDS = ("src_ip",)
SENSOR_FIELDS = ("dst_ip",)


class AddressMap:
    """Bildet echte Adressen deterministisch auf Dokumentationsadressen ab."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._next_v4 = 0
        self._next_v6 = 0

    def for_attacker(self, value: str) -> str:
        if value in self._map:
            return self._map[value]
        address = self._public(value)
        if address is None:
            return value
        if address.version == 4:
            replacement = str(ATTACKER_V4 + self._next_v4)
            self._next_v4 += 1
        else:
            replacement = str(ATTACKER_V6 + self._next_v6)
            self._next_v6 += 1
        self._map[value] = replacement
        return replacement

    def for_sensor(self, value: str) -> str:
        if value in self._map:
            return self._map[value]
        address = self._public(value)
        if address is None:
            return value
        self._map[value] = SENSOR_V4 if address.version == 4 else SENSOR_V6
        return self._map[value]

    @staticmethod
    def _public(value: str) -> ipaddress._BaseAddress | None:
        """Gibt die Adresse zurück, wenn sie öffentlich ist, sonst None.

        Loopback und private Adressen bleiben stehen: Sie gehören niemandem
        außerhalb des Sensors, und an ``127.0.0.1`` erkennen wir später unsere
        eigenen Testsitzungen (Schritt 7.1).
        """
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return None
        return address if address.is_global else None

    def replace_everywhere(self, text: str) -> str:
        """Ersetzt alle bekannten Adressen, längste zuerst.

        Ohne die Sortierung würde ``10.1.1.1`` einen Treffer in ``10.1.1.10``
        zerschneiden.
        """
        for original in sorted(self._map, key=len, reverse=True):
            text = text.replace(original, self._map[original])
        return text

    def __len__(self) -> int:
        return len(self._map)


def read_events(patterns: Iterable[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict) and "eventid" in event:
                        events.append(event)
    return events


def classify(events: list[dict[str, Any]]) -> str:
    """Grobe Einteilung einer Sitzung, nur für die Auswahl der Beispiele."""
    ids = {event["eventid"] for event in events}
    if "cowrie.command.input" in ids:
        return "mit_befehlen"
    if "cowrie.login.success" in ids:
        return "login_ohne_befehl"
    if "cowrie.login.failed" in ids:
        return "login_fehlgeschlagen"
    return "nur_verbindung"


def pick_sessions(
    by_session: dict[str, list[dict[str, Any]]], per_kind: int
) -> list[str]:
    """Wählt je Art einige Sitzungen aus, bevorzugt verschiedene Clients."""
    chosen: list[str] = []
    for kind in ("mit_befehlen", "login_ohne_befehl", "login_fehlgeschlagen", "nur_verbindung"):
        candidates = [s for s, evs in by_session.items() if classify(evs) == kind]
        seen_clients: set[str] = set()
        picked: list[str] = []
        for session in sorted(candidates, key=lambda s: by_session[s][0].get("timestamp", "")):
            client = next(
                (e.get("version", "") for e in by_session[session] if e["eventid"] == "cowrie.client.version"),
                "",
            )
            # Erst je Client einen, danach auffüllen.
            if client in seen_clients and len(picked) >= per_kind // 2:
                continue
            seen_clients.add(client)
            picked.append(session)
            if len(picked) >= per_kind:
                break
        chosen.extend(picked)
    return chosen


def anonymize(events: list[dict[str, Any]], addresses: AddressMap) -> list[dict[str, Any]]:
    # Erst die Karte vollständig aufbauen, bevor irgendein Text ersetzt wird.
    # Dabei erst die Adresse des Sensors, dann die der Angreifer: Träfe eine Adresse
    # auf beide Rollen zu, soll sie als Sensor gelten.
    for field in SENSOR_FIELDS:
        for event in events:
            if isinstance(event.get(field), str):
                addresses.for_sensor(event[field])
    for field in SOURCE_FIELDS:
        for event in events:
            if isinstance(event.get(field), str):
                addresses.for_attacker(event[field])

    cleaned: list[dict[str, Any]] = []
    for event in events:
        as_text = json.dumps(event, ensure_ascii=False, sort_keys=True)
        cleaned.append(json.loads(addresses.replace_everywhere(as_text)))
    return cleaned


def contains_public_address(events: list[dict[str, Any]], fields: Iterable[str]) -> bool:
    """Sicherung: In den genannten Feldern darf keine öffentliche Adresse stehen."""
    for event in events:
        for field in fields:
            value = event.get(field)
            if not isinstance(value, str):
                continue
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if address.is_global:
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", default=DEFAULT_LOGS, help="Glob auf die Logdateien")
    parser.add_argument("--per-kind", type=int, default=6, help="Sitzungen je Art")
    parser.add_argument("--max-events", type=int, default=800, help="Obergrenze für Zeilen")
    args = parser.parse_args()

    events = read_events([args.logs])
    if not events:
        print("Keine Ereignisse gefunden. Stimmt der Pfad?", file=sys.stderr)
        return 1

    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        session = event.get("session")
        if isinstance(session, str):
            by_session[session].append(event)
    for session_events in by_session.values():
        session_events.sort(key=lambda e: e.get("timestamp", ""))

    chosen = pick_sessions(by_session, args.per_kind)
    selected = [event for session in chosen for event in by_session[session]]
    selected.sort(key=lambda e: e.get("timestamp", ""))
    selected = selected[: args.max_events]

    addresses = AddressMap()
    cleaned = anonymize(selected, addresses)

    if contains_public_address(cleaned, SOURCE_FIELDS + SENSOR_FIELDS):
        print("Abbruch: Es blieb eine öffentliche Adresse stehen.", file=sys.stderr)
        return 2

    for event in cleaned:
        print(json.dumps(event, ensure_ascii=False, sort_keys=True))

    kinds = Counter(classify(by_session[s]) for s in chosen)
    eventids = Counter(e["eventid"] for e in cleaned)
    print(
        f"Sitzungen gesamt im Log: {len(by_session)}, ausgewählt: {len(chosen)}",
        file=sys.stderr,
    )
    print(f"Arten: {dict(kinds)}", file=sys.stderr)
    print(f"Zeilen: {len(cleaned)}, ersetzte Adressen: {len(addresses)}", file=sys.stderr)
    print(f"Ereignisarten: {dict(eventids)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
