"""Befehle den Techniken von MITRE ATT&CK zuordnen (Schritt 6.1, E-037).

Die Regeln stehen als Daten in ``server/rules/attack.yml``, nicht im Code.
Dieses Modul lädt und prüft sie und wendet sie an. Alles hier ist reine
Rechnung ohne Datenbank.

Die Befehle stammen von Angreifern und laufen gegen reguläre Ausdrücke. Damit
niemand die API mit einem präparierten Befehl ausbremst (ReDoS), gilt:

- Der Befehl wird vor dem Abgleich auf ``MAX_INPUT`` Zeichen gekürzt.
- Beim Laden wird jedes Muster zerlegt. Eine Wiederholung in einer
  Wiederholung, etwa ``(a+)+``, und Rückverweise lassen die ganze Datei
  scheitern. Beim Start der API fällt das sofort auf, nicht erst beim ersten
  Befehl.

Der Befehl wird nur gelesen, nie ausgeführt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Interne Module, nur um Muster vor dem Übersetzen zu zerlegen.
from re import _constants as sre_constants
from re import _parser as sre_parse
from typing import Any

import yaml

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "attack.yml"

# Längere Befehle werden nur bis hier abgeglichen. Echte Befehle mit einer
# Technik sind weit kürzer; alles darüber ist Füllmaterial oder ein Angriff
# auf die Auswertung.
MAX_INPUT = 4096

MAX_RULES = 200
MAX_PATTERNS = 16
MAX_PATTERN_LENGTH = 512
MAX_NAME_LENGTH = 128
MAX_REASON_LENGTH = 300

TECHNIQUE_ID = re.compile(r"^T\d{4}(?:\.\d{3})?$")
VERSION = re.compile(r"^\d{1,3}\.\d{1,3}$")

# Die 15 Taktiken von Enterprise ATT&CK v19. „Defense Evasion“ gibt es seit
# v19 nicht mehr, sie ist in Stealth und Defense Impairment aufgegangen.
TACTICS = frozenset(
    {
        "Reconnaissance",
        "Resource Development",
        "Initial Access",
        "Execution",
        "Persistence",
        "Privilege Escalation",
        "Stealth",
        "Defense Impairment",
        "Credential Access",
        "Discovery",
        "Lateral Movement",
        "Collection",
        "Command and Control",
        "Exfiltration",
        "Impact",
    }
)

# Platzhalter aus der Regeldatei, siehe dort.
PLACEHOLDERS = {
    "{cmd}": (
        r"(?:^|[;&|({`\n]|\$\()\s*"
        r"(?:(?:sudo|busybox|nohup|exec|command|then|do|else)\s+)?"
        r"(?:/(?:usr/)?(?:local/)?s?bin/)?"
    ),
    "{end}": r"(?![^\s;&|)}`<>])",
}

_REPEATS = {
    sre_constants.MAX_REPEAT,
    sre_constants.MIN_REPEAT,
    sre_constants.POSSESSIVE_REPEAT,
}
_BACKREFERENCES = {
    sre_constants.GROUPREF,
    sre_constants.GROUPREF_EXISTS,
    sre_constants.GROUPREF_IGNORE,
    sre_constants.GROUPREF_LOC_IGNORE,
    sre_constants.GROUPREF_UNI_IGNORE,
}


class RulesError(ValueError):
    """Die Regeldatei ist ungültig. Die Meldung nennt Regel und Grund."""


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    tactics: tuple[str, ...]
    reason: str
    patterns: tuple[re.Pattern[str], ...]

    def matches(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.patterns)


@dataclass(frozen=True)
class RuleSet:
    attack_version: str
    rules: tuple[Rule, ...]

    def classify(self, text: Any) -> list[str]:
        """IDs aller Techniken, die der Befehl trifft, sortiert. Sonst ``[]``."""
        if not isinstance(text, str) or not text.strip():
            return []
        sample = text[:MAX_INPUT]
        return sorted({rule.id for rule in self.rules if rule.matches(sample)})


# --- Laden und prüfen ----------------------------------------------------------


def _children(value: Any) -> list[sre_parse.SubPattern]:
    if isinstance(value, sre_parse.SubPattern):
        return [value]
    if isinstance(value, (tuple, list)):
        return [child for item in value for child in _children(item)]
    return []


def _check_structure(parsed: sre_parse.SubPattern, inside_repeat: bool = False) -> None:
    """Wirft ``RulesError`` bei verschachtelten Wiederholungen und Rückverweisen.

    ``?`` zählt nicht als Wiederholung: Ein optionaler Teil mit ``\\s+`` darin
    kann höchstens einmal vorkommen und bringt keine Rückverfolgung ins
    Quadrat.
    """
    for op, av in parsed:
        if op in _BACKREFERENCES:
            raise RulesError("Rückverweise sind nicht erlaubt")
        if op in _REPEATS:
            _low, high, inner = av
            many = high > 1
            if many and inside_repeat:
                raise RulesError("verschachtelte Wiederholung")
            _check_structure(inner, inside_repeat or many)
            continue
        for child in _children(av):
            _check_structure(child, inside_repeat)


def compile_pattern(source: Any) -> re.Pattern[str]:
    if not isinstance(source, str) or not source:
        raise RulesError("Muster ist leer oder kein Text")
    if len(source) > MAX_PATTERN_LENGTH:
        raise RulesError(f"Muster länger als {MAX_PATTERN_LENGTH} Zeichen")
    expanded = source
    for placeholder, replacement in PLACEHOLDERS.items():
        expanded = expanded.replace(placeholder, replacement)
    try:
        _check_structure(sre_parse.parse(expanded))
        return re.compile(expanded)
    except re.error as exc:
        raise RulesError(f"Muster lässt sich nicht übersetzen ({exc.msg})") from None


def _text(entry: dict[str, Any], key: str, limit: int, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RulesError(f"{where}: {key} fehlt")
    if len(value) > limit:
        raise RulesError(f"{where}: {key} länger als {limit} Zeichen")
    return value.strip()


def parse_rule(entry: Any, index: int) -> Rule:
    where = f"Regel {index + 1}"
    if not isinstance(entry, dict):
        raise RulesError(f"{where}: kein Objekt")
    technique = entry.get("id")
    if not isinstance(technique, str) or not TECHNIQUE_ID.match(technique):
        raise RulesError(f"{where}: ungültige Technik-ID")
    where = f"Regel {technique}"

    tactics = entry.get("tactics")
    if not isinstance(tactics, list) or not tactics:
        raise RulesError(f"{where}: tactics fehlt")
    unknown = [t for t in tactics if t not in TACTICS]
    if unknown:
        raise RulesError(f"{where}: unbekannte Taktik {unknown[0]!r}")

    patterns = entry.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise RulesError(f"{where}: patterns fehlt")
    if len(patterns) > MAX_PATTERNS:
        raise RulesError(f"{where}: mehr als {MAX_PATTERNS} Muster")
    compiled = []
    for number, source in enumerate(patterns, start=1):
        try:
            compiled.append(compile_pattern(source))
        except RulesError as exc:
            raise RulesError(f"{where}, Muster {number}: {exc}") from None

    return Rule(
        id=technique,
        name=_text(entry, "name", MAX_NAME_LENGTH, where),
        tactics=tuple(tactics),
        reason=_text(entry, "reason", MAX_REASON_LENGTH, where),
        patterns=tuple(compiled),
    )


def parse_rules(data: Any) -> RuleSet:
    if not isinstance(data, dict):
        raise RulesError("Regeldatei ist kein Objekt")
    version = data.get("attack_version")
    if not isinstance(version, str) or not VERSION.match(version):
        raise RulesError("attack_version fehlt oder ist ungültig")
    entries = data.get("rules")
    if not isinstance(entries, list) or not entries:
        raise RulesError("rules fehlt")
    if len(entries) > MAX_RULES:
        raise RulesError(f"mehr als {MAX_RULES} Regeln")
    rules = tuple(parse_rule(entry, index) for index, entry in enumerate(entries))
    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            raise RulesError(f"Regel {rule.id} doppelt")
        seen.add(rule.id)
    return RuleSet(attack_version=version, rules=rules)


def load_rules(path: Path = RULES_PATH) -> RuleSet:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulesError(f"{path.name} ist kein gültiges YAML") from exc
    return parse_rules(data)


@lru_cache(maxsize=1)
def default_rules() -> RuleSet:
    """Die Regeln aus ``RULES_PATH``, einmal geladen."""
    return load_rules()


def classify(text: Any) -> list[str]:
    """Techniken eines Befehls nach den Standardregeln."""
    return default_rules().classify(text)
