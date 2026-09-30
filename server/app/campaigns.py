"""Sitzungen zu Kampagnen bündeln (Schritt 6.2, E-039).

Eine Kampagne ist eine Gruppe von Sitzungen, die dieselbe Folge von Befehlen
schicken, also sehr wahrscheinlich dasselbe Werkzeug. Bots setzen in ihre
Befehle aber Zufallswerte ein: ein neues Passwort, einen Ordnernamen, eine
andere Download-Adresse. Deshalb werden die Befehle vor dem Vergleich
normalisiert, und der Fingerprint einer Sitzung ist der Hash über die Folge
der normalisierten Befehle. Details und Grenzen stehen in docs/campaigns.md.

Alles hier ist reine Rechnung ohne Datenbank. Die Befehle stammen von
Angreifern und laufen gegen reguläre Ausdrücke. Gegen ReDoS gilt dasselbe wie
in ``app/attack.py`` (E-037): Die Eingabe wird gekürzt, in Wiederholungen
stehen nur Zeichenklassen, und die Tests prüfen jedes Muster mit derselben
Strukturprüfung. Die Läufe sind zusätzlich possessiv und beginnen nur an
Wortgrenzen, damit kein Muster mitten in einem langen Lauf neu ansetzt.

Die Normalisierung ersetzt nur Teile durch Platzhalter. Sie baut die
Entschärfung nie zurück: Aus ``hxxp://`` oder ``[.]`` wird nie wieder eine
klickbare Adresse.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

LABELS_PATH = Path(__file__).resolve().parents[1] / "rules" / "campaigns.yml"

# So lang kann ein gespeicherter Befehl höchstens sein (LIMITS["input"] in
# app/events.py). Längeres wird vorsichtshalber gekürzt.
MAX_INPUT = 8192

# Erst ab so vielen Sitzungen mit gleichem Fingerprint entsteht eine Kampagne.
MIN_SESSIONS = 5

KINDS = ("exec", "interactive")

# Länge des Präfixes, über das ein Label seinen Fingerprint findet.
PREFIX_LENGTH = 12
MAX_LABELS = 500
MAX_LABEL_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1000

# --- Normalisierung --------------------------------------------------------------

# Öffentliche SSH-Schlüssel. Der Body ist Base64 und beginnt bei OpenSSH immer
# mit "AAAA" (Längenfeld mit führenden Nullbytes).
SSH_KEY = re.compile(
    r"(?<![\w-])"
    r"(?P<type>ssh-rsa|ssh-dss|ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384"
    r"|ecdsa-sha2-nistp521|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)"
    r"\s++"
    r"(?P<body>AAAA[A-Za-z0-9+/]{16,}+={0,3})",
    re.ASCII,
)
WHITESPACE = re.compile(r"\s+")
# Entschärfte URLs wie aus app/defang.py. Sie enden an denselben Zeichen und
# zusätzlich an ; & und Backtick, damit der nächste Befehl stehen bleibt.
URL = re.compile(r"\b(?:hxxps?|fxp|tfxp)://[^\s\"'<>\\|);&`]*+", re.IGNORECASE)
# Entschärfte IPv4-Adressen: 198[.]51[.]100[.]7
IPV4 = re.compile(
    r"(?<!\w)\d{1,3}\[\.\]\d{1,3}\[\.\]\d{1,3}\[\.\]\d{1,3}(?!\w)",
    re.ASCII,
)
# "user:passwort", etwa vor chpasswd. Der Name bleibt, das Passwort nicht.
# Kein Treffer, wenn hinter dem Doppelpunkt ein Pfad beginnt ($PATH:/usr/bin).
USER_PASSWORD = re.compile(
    r"(?<![\w/.\-])(?P<user>[A-Za-z_][\w.\-]{0,31}+):(?!/)[^\s:\"'`|;&\\<>()]++",
    re.ASCII,
)
HEX = re.compile(r"(?<!\w)[0-9A-Fa-f]{16,}+(?!\w)", re.ASCII)
# Buchstaben und Ziffern gemischt, mindestens acht Zeichen.
TOKEN = re.compile(
    r"(?<!\w)(?=[A-Za-z]*+\d)(?=\d*+[A-Za-z])[A-Za-z0-9]{8,}+(?!\w)",
    re.ASCII,
)
# Freistehende Zahlen. Ziffern in einem Wort (python3, x86_64) bleiben.
NUMBER = re.compile(r"(?<!\w)\d++(?!\w)", re.ASCII)

# Reihenfolge zählt: Erst die großen Stücke (URL enthält IP, Passwort kann
# Ziffern enthalten), dann die kleinen. Kein Platzhalter enthält Ziffern oder
# einen Doppelpunkt, spätere Schritte lassen ihn also in Ruhe.
PATTERNS = (
    (URL, "<URL>"),
    (IPV4, "<IP>"),
    (USER_PASSWORD, r"\g<user>:<PW>"),
    (HEX, "<HEX>"),
    (TOKEN, "<TOKEN>"),
    (NUMBER, "<N>"),
)


def key_placeholder(body: str) -> str:
    """Ein Schlüssel wird zu einem Platzhalter, der ihn wiedererkennt.

    Verschiedene Schlüssel gehören zu verschiedenen Angreifern und sollen
    verschiedene Kampagnen bleiben.
    """
    return f"<KEY:{sha256(body.encode('ascii')).hexdigest()[:12]}>"


def _normalize_plain(text: str) -> str:
    text = WHITESPACE.sub(" ", text)
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def normalize(command: Any) -> str:
    """Ein Befehl in der Form, in der Bots mit Zufallswerten gleich aussehen."""
    if not isinstance(command, str):
        return ""
    text = command[:MAX_INPUT]
    # Die Schlüssel zuerst heraustrennen und die übrigen Regeln nur auf die
    # Stücke dazwischen anwenden. Sonst würden die Hex-Zeichen im Platzhalter
    # zu <TOKEN>, und alle Schlüssel sähen wieder gleich aus.
    parts: list[str] = []
    position = 0
    for match in SSH_KEY.finditer(text):
        parts.append(_normalize_plain(text[position : match.start()]))
        parts.append(f"{match.group('type')} {key_placeholder(match.group('body'))}")
        position = match.end()
    parts.append(_normalize_plain(text[position:]))
    return WHITESPACE.sub(" ", "".join(parts)).strip()


def normalized_sequence(commands: Iterable[Any]) -> list[str]:
    """Normalisierte Befehle, leere weggelassen, direkte Wiederholungen einmal."""
    sequence: list[str] = []
    for command in commands:
        normalized = normalize(command)
        if normalized and (not sequence or sequence[-1] != normalized):
            sequence.append(normalized)
    return sequence


def fingerprint(kind: str, sequence: list[str]) -> str | None:
    """SHA-256 über Art der Sitzung und Befehlsfolge. Ohne Befehle ``None``.

    Die Art gehört dazu (E-039): Dieselben Befehle per Exec und in einer Shell
    kommen in der Praxis von verschiedenen Werkzeugen, und eine Kampagne hat
    genau eine Art. Normalisierte Befehle enthalten keinen Zeilenumbruch, die
    Trennung ist also eindeutig.
    """
    if kind not in KINDS:
        raise ValueError(f"unbekannte Art {kind!r}")
    if not sequence:
        return None
    return sha256("\n".join([kind, *sequence]).encode("utf-8")).hexdigest()


def opening_hash(sequence: list[str], count: int = 3) -> str:
    """Kurzer Hash über die ersten Befehle, nur für den Bericht.

    Teilen sich mehrere Kampagnen denselben Wert, beginnen sie gleich und
    laufen erst später auseinander (siehe docs/campaigns.md, Grenzen).
    """
    return sha256("\n".join(sequence[:count]).encode("utf-8")).hexdigest()[:6]


# --- Labels ------------------------------------------------------------------------

PREFIX = re.compile(r"^[0-9a-f]{12}$")


class LabelsError(ValueError):
    """Die Label-Datei ist ungültig. Die Meldung nennt Eintrag und Grund."""


@dataclass(frozen=True)
class Label:
    label: str
    description: str


def _printable(value: str, allow_newlines: bool) -> bool:
    return all(ch.isprintable() or (allow_newlines and ch == "\n") for ch in value)


def _label_text(entry: dict[str, Any], key: str, limit: int, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LabelsError(f"{where}: {key} fehlt")
    value = value.strip()
    if len(value) > limit:
        raise LabelsError(f"{where}: {key} länger als {limit} Zeichen")
    if not _printable(value, allow_newlines=key == "description"):
        raise LabelsError(f"{where}: {key} enthält Steuerzeichen")
    return value


def parse_labels(data: Any) -> dict[str, Label]:
    if not isinstance(data, dict) or set(data) != {"campaigns"}:
        raise LabelsError("Label-Datei braucht genau den Schlüssel campaigns")
    entries = data["campaigns"]
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise LabelsError("campaigns ist keine Liste")
    if len(entries) > MAX_LABELS:
        raise LabelsError(f"mehr als {MAX_LABELS} Labels")

    labels: dict[str, Label] = {}
    names: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        where = f"Eintrag {index}"
        if not isinstance(entry, dict):
            raise LabelsError(f"{where}: kein Objekt")
        unknown = set(entry) - {"prefix", "label", "description"}
        if unknown:
            raise LabelsError(f"{where}: unbekannter Schlüssel {sorted(unknown)[0]!r}")
        prefix = entry.get("prefix")
        if not isinstance(prefix, str) or not PREFIX.match(prefix):
            raise LabelsError(f"{where}: prefix muss aus 12 kleinen Hex-Zeichen bestehen")
        where = f"Eintrag {prefix}"
        if prefix in labels:
            raise LabelsError(f"{where}: prefix doppelt")
        label = _label_text(entry, "label", MAX_LABEL_LENGTH, where)
        # Das Frontend nutzt das Label als Schlüssel einer Liste.
        if label in names:
            raise LabelsError(f"{where}: label doppelt")
        names.add(label)
        labels[prefix] = Label(
            label=label,
            description=_label_text(entry, "description", MAX_DESCRIPTION_LENGTH, where),
        )
    return labels


def load_labels(path: Path = LABELS_PATH) -> dict[str, Label]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LabelsError(f"{path.name} ist kein gültiges YAML") from exc
    return parse_labels(data)
