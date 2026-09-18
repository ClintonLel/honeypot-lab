"""Cowrie-Ereignisse prüfen und in eine speicherbare Form bringen.

Alles hier ist reine Rechnung ohne Datenbank, damit es sich auch ohne
PostgreSQL testen lässt. Die Eingaben stammen von einem Honeypot, also aus
feindlicher Quelle (README „Harte Regeln“): Jede Zeile wird gegen eine Liste
bekannter ``eventid`` geprüft, jede Länge begrenzt, jeder Freitext entschärft.

Die Quell-IP verlässt dieses Modul nur in ``NormalizedEvent.source_address``.
Der Ingest reichert damit an, bildet den HMAC und wirft den Klartext weg
(E-009, E-022). In ``payload`` steht sie nie, auch nicht in Freitexten.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from ipaddress import ip_address
from typing import Any

from app.defang import defang, shorten

# Ereignisse, die Cowrie schreibt und die wir auswerten. Alles andere lehnen
# wir ab, statt es blind zu speichern.
KNOWN_EVENTIDS = frozenset(
    {
        "cowrie.session.connect",
        "cowrie.session.closed",
        "cowrie.session.params",
        "cowrie.session.file_download",
        "cowrie.session.file_upload",
        "cowrie.client.version",
        "cowrie.client.kex",
        "cowrie.client.size",
        "cowrie.client.fingerprint",
        "cowrie.login.success",
        "cowrie.login.failed",
        "cowrie.command.input",
        "cowrie.command.failed",
        "cowrie.log.closed",
        "cowrie.direct-tcpip.request",
        "cowrie.direct-tcpip.data",
    }
)

# Sensorname aus cowrie.cfg -> Variante des Experiments (E-002).
SENSOR_VARIANTS = {"hp-a": "a", "hp-b": "b"}

# Obergrenzen je Feld. Längere Werte werden gekürzt, nicht abgelehnt: Ein zu
# langer Befehl ist ein Befund, kein Grund, die Zeile wegzuwerfen.
LIMITS = {
    "message": 2048,
    "input": 8192,
    "username": 128,
    "password": 128,
    "version": 128,
    "hassh": 32,
    "arch": 64,
    "shasum": 64,
    "url": 2048,
    "text": 1024,
}

# Felder, die erst auf dem Transportweg dazukommen (Vector). Sie gehören nicht
# in den Hash, sonst wäre dieselbe Zeile nach einem Neustart nicht mehr als
# Dublette erkennbar.
TRANSPORT_KEYS = frozenset({"host", "source_type", "file", "offset", "variant", "timestamp_received"})

# Felder mit Adressen der Beteiligten. Sie werden nie gespeichert.
ADDRESS_KEYS = frozenset({"src_ip", "dst_ip", "peer_ip"})

# Platzhalter für die Adressen der Beteiligten. Cowrie schreibt sie auch in
# Freitexte ("New connection: 1.2.3.4:59386 (5.6.7.8:2222)"). Entschärfen
# genügt dort nicht: "1[.]2[.]3[.]4" ist immer noch die Adresse.
REDACTIONS = {"src_ip": "<src>", "dst_ip": "<dst>", "peer_ip": "<peer>"}

SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SENSOR_NAME = re.compile(r"^[a-z0-9-]{1,32}$")

# Zeitfenster, in dem ein Ereignis liegen muss. Der Puffer nach vorn fängt
# leichte Uhrabweichungen des Sensors ab.
EARLIEST = datetime(2020, 1, 1, tzinfo=timezone.utc)
FUTURE_TOLERANCE = timedelta(hours=1)

MAX_BATCH = 500

# PostgreSQL speichert kein NUL-Byte, weder in text noch in jsonb. Angreifer
# schicken es trotzdem, etwa in Benutzernamen. Statt die Zeile zu verlieren,
# steht an der Stelle das sichtbare Zeichen für NUL.
NUL = "\x00"
NUL_MARK = "\u2400"


class EventRejected(ValueError):
    """Ein Ereignis hat die Prüfung nicht bestanden."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class NormalizedEvent:
    """Ein geprüftes Ereignis, fertig zum Speichern."""

    dedup_hash: str
    eventid: str
    occurred_at: datetime
    cowrie_session: str
    sensor: str
    variant: str
    payload: dict[str, Any]
    # Nur für die Anreicherung, wird nach dem Hashen verworfen.
    source_address: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


def dedup_hash(raw: dict[str, Any]) -> str:
    """Hash über den Inhalt eines Ereignisses.

    Cowries ``uuid`` taugt dafür nicht: Sie kennzeichnet die Instanz, nicht das
    Ereignis, und ist für alle Zeilen gleich.
    """
    material = {key: value for key, value in raw.items() if key not in TRANSPORT_KEYS}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def parse_timestamp(value: Any, now: datetime | None = None) -> datetime:
    if not isinstance(value, str):
        raise EventRejected("timestamp fehlt")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventRejected("timestamp nicht lesbar") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    now = now or datetime.now(tz=timezone.utc)
    if parsed < EARLIEST:
        raise EventRejected("timestamp liegt zu weit zurück")
    if parsed > now + FUTURE_TOLERANCE:
        raise EventRejected("timestamp liegt in der Zukunft")
    return parsed


def variant_of(raw: dict[str, Any]) -> str:
    """Variante aus dem Feld ``variant`` oder aus dem Sensornamen."""
    explicit = raw.get("variant")
    if isinstance(explicit, str) and explicit in ("a", "b"):
        return explicit
    sensor = raw.get("sensor")
    if isinstance(sensor, str) and sensor in SENSOR_VARIANTS:
        return SENSOR_VARIANTS[sensor]
    raise EventRejected("Variante nicht bestimmbar")


def clean_text(value: Any, limit_key: str, pairs: list[tuple[str, str]] | None = None) -> str | None:
    """Kürzt einen Freitext, entfernt die Adressen der Beteiligten, entschärft."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    shortened = shorten(without_nul(value), LIMITS.get(limit_key, LIMITS["text"]))
    return defang(redact(shortened, pairs or []))


def redactions_for(raw: dict[str, Any]) -> list[tuple[str, str]]:
    """Adressen der Beteiligten mit ihrem Platzhalter, längste zuerst."""
    pairs = [
        (raw[key], placeholder)
        for key, placeholder in REDACTIONS.items()
        if isinstance(raw.get(key), str) and raw[key]
    ]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def redact(text: str, pairs: list[tuple[str, str]]) -> str:
    for address, placeholder in pairs:
        text = text.replace(address, placeholder)
    return text


def without_nul(text: str) -> str:
    return text.replace(NUL, NUL_MARK) if NUL in text else text


def defang_payload(value: Any, pairs: list[tuple[str, str]], depth: int = 0) -> Any:
    """Entfernt die Adressen der Beteiligten und entschärft jeden Text."""
    if depth > 6:
        return None
    if isinstance(value, str):
        return defang(redact(shorten(without_nul(value), LIMITS["input"]), pairs))
    if isinstance(value, dict):
        return {
            without_nul(str(k))[:64]: defang_payload(v, pairs, depth + 1)
            for k, v in list(value.items())[:64]
        }
    if isinstance(value, list):
        return [defang_payload(v, pairs, depth + 1) for v in value[:64]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[: LIMITS["text"]]


def normalize(raw: Any, now: datetime | None = None) -> NormalizedEvent:
    """Prüft ein Ereignis und gibt die speicherbare Fassung zurück."""
    if not isinstance(raw, dict):
        # Der Typ im Grund macht Formfehler im Log sofort erkennbar (E-027).
        raise EventRejected(f"kein Objekt ({type(raw).__name__})")

    eventid = raw.get("eventid")
    if not isinstance(eventid, str) or eventid not in KNOWN_EVENTIDS:
        raise EventRejected("unbekannte eventid")

    session = raw.get("session")
    if not isinstance(session, str) or not SESSION_ID.match(session):
        raise EventRejected("session fehlt oder ist ungültig")

    sensor = raw.get("sensor")
    if not isinstance(sensor, str) or not SENSOR_NAME.match(sensor):
        raise EventRejected("sensor fehlt oder ist ungültig")

    occurred_at = parse_timestamp(raw.get("timestamp"), now=now)
    variant = variant_of(raw)

    source_address = raw.get("src_ip")
    if source_address is not None:
        if not isinstance(source_address, str):
            raise EventRejected("src_ip ist keine Zeichenkette")
        try:
            ip_address(source_address)
        except ValueError as exc:
            raise EventRejected("src_ip ist keine Adresse") from exc
    elif eventid == "cowrie.session.connect":
        raise EventRejected("src_ip fehlt bei session.connect")

    # Der Hash entsteht vor dem Entfernen der Adressen: Er soll die Zeile
    # kennzeichnen, wie der Sensor sie geschrieben hat.
    digest = dedup_hash(raw)

    pairs = redactions_for(raw)
    payload = {key: value for key, value in raw.items() if key not in ADDRESS_KEYS and key not in TRANSPORT_KEYS}
    payload = defang_payload(payload, pairs)

    return NormalizedEvent(
        dedup_hash=digest,
        eventid=eventid,
        occurred_at=occurred_at,
        cowrie_session=session,
        sensor=sensor,
        variant=variant,
        payload=payload,
        source_address=source_address,
        fields=extract_fields(raw, pairs),
    )


def extract_fields(raw: dict[str, Any], pairs: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Zieht die Felder heraus, die in Sitzungen und Befehle wandern."""
    pairs = pairs if pairs is not None else redactions_for(raw)
    out: dict[str, Any] = {}
    for key in ("username", "password", "version", "hassh", "arch", "shasum"):
        if key in raw:
            out[key] = clean_text(raw[key], key, pairs)
    if "input" in raw:
        out["input"] = clean_text(raw["input"], "input", pairs)
    if "url" in raw:
        out["url"] = clean_text(raw["url"], "url", pairs)
    for key in ("duration_ms", "width", "height", "size"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = int(value)
    return out
