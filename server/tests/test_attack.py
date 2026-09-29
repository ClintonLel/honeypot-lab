"""Prüft die ATT&CK-Regeln und ihre Anwendung (Schritt 6.1, ohne Datenbank).

Die Befehle stehen in ``fixtures/attack_commands.yml``. Sie sind von Hand
geschrieben, nicht aus Rohdaten übernommen. Je Regel gibt es mindestens einen
Treffer und einen Beinahe-Treffer.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from app.attack import (
    MAX_INPUT,
    RULES_PATH,
    TACTICS,
    RulesError,
    classify,
    compile_pattern,
    default_rules,
    load_rules,
    parse_rules,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "attack_commands.yml"
CASES = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
RULES = default_rules()

HITS = [(technique, command) for technique, group in CASES["techniques"].items() for command in group["hits"]]
NEAR_MISSES = [
    (technique, command) for technique, group in CASES["techniques"].items() for command in group["near_misses"]
]


# --- Regeldatei ----------------------------------------------------------------


def test_the_rules_name_their_attack_version():
    assert RULES.attack_version == "19.2"
    assert "ATT&CK Enterprise v19.2" in RULES_PATH.read_text(encoding="utf-8").splitlines()[0]


def test_every_rule_is_complete():
    for rule in RULES.rules:
        assert rule.name and rule.reason and rule.patterns
        assert set(rule.tactics) <= TACTICS


def test_the_start_set_is_there():
    ids = {rule.id for rule in RULES.rules}
    assert {"T1082", "T1033", "T1098.004", "T1222.002", "T1105"} <= ids


def test_every_rule_has_a_hit_and_a_near_miss():
    ids = {rule.id for rule in RULES.rules}
    assert set(CASES["techniques"]) == ids
    for technique, group in CASES["techniques"].items():
        assert group["hits"], technique
        assert group["near_misses"], technique


def test_the_fixture_contains_no_live_address():
    text = FIXTURE.read_text(encoding="utf-8")
    assert "http://" not in text and "https://" not in text
    assert "198.51" not in text and "203.0" not in text and "192.0" not in text


# --- Zuordnung -------------------------------------------------------------------


@pytest.mark.parametrize(("technique", "command"), HITS)
def test_a_hit_finds_exactly_its_technique(technique, command):
    assert classify(command) == [technique]


@pytest.mark.parametrize(("technique", "command"), NEAR_MISSES)
def test_a_near_miss_finds_nothing(technique, command):
    assert classify(command) == []


@pytest.mark.parametrize("case", CASES["multi"], ids=lambda case: ",".join(case["expect"]))
def test_one_command_can_hit_several_techniques(case):
    assert classify(case["command"]) == case["expect"]


@pytest.mark.parametrize("empty", ["", " ", "\n\t", None, 42, ["uname"]])
def test_empty_or_odd_input_has_no_technique(empty):
    assert classify(empty) == []


def test_an_overlong_command_is_only_read_up_to_the_limit():
    filler = "x" * (MAX_INPUT * 25)
    started = time.perf_counter()
    assert classify("uname -a; " + filler) == ["T1082"]
    assert classify(filler + "; uname -a") == []
    # Ein Treffer knapp vor der Grenze zählt noch.
    assert classify("x" * (MAX_INPUT - 20) + "; whoami") == ["T1033"]
    assert time.perf_counter() - started < 1.0


# --- ReDoS -----------------------------------------------------------------------

# Eingaben, die bei schlecht gebauten Mustern viel Rückverfolgung auslösen:
# viele Anfangs- oder Umleitungszeichen, viele Befehlswörter ohne Ende.
HOSTILE = [
    ";" * MAX_INPUT,
    ">" * MAX_INPUT,
    " " * MAX_INPUT,
    "$(" * (MAX_INPUT // 2),
    "curl " * (MAX_INPUT // 5),
    "chmod " * (MAX_INPUT // 6),
    "tee " * (MAX_INPUT // 4),
    "unset " * (MAX_INPUT // 6),
    "/" * MAX_INPUT,
    "a" * MAX_INPUT,
    "curl -" + "a" * (MAX_INPUT - 6),
    "> " + "a/" * (MAX_INPUT // 2 - 1),
    "chmod " + "x" * (MAX_INPUT - 6),
]


@pytest.mark.parametrize("hostile", HOSTILE, ids=lambda text: repr(text[:8]))
def test_hostile_input_is_fast(hostile):
    started = time.perf_counter()
    for _ in range(5):
        RULES.classify(hostile)
    assert (time.perf_counter() - started) / 5 < 0.1


@pytest.mark.parametrize(
    "pattern",
    [r"(a+)+", r"(?:\s*x)*", r"(?:a|b+){2,}", r"(\w)\1", r"(?P<x>a)(?P=x)"],
)
def test_dangerous_patterns_are_refused(pattern):
    with pytest.raises(RulesError):
        compile_pattern(pattern)


def test_an_optional_group_may_contain_a_repeat():
    # {cmd} selbst hat so einen Teil: (?:sudo\s+)?
    assert compile_pattern(r"{cmd}(?:x\s+)?y").search("x  y")


# --- Kaputte Regeldateien ---------------------------------------------------------


def valid() -> dict:
    return {
        "attack_version": "19.2",
        "rules": [
            {
                "id": "T1082",
                "name": "System Information Discovery",
                "tactics": ["Discovery"],
                "reason": "Test",
                "patterns": ["{cmd}uname{end}"],
            }
        ],
    }


def broken(**changes) -> dict:
    data = valid()
    data["rules"][0].update(changes)
    return data


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"rules": valid()["rules"]},
        {**valid(), "attack_version": "neu"},
        {**valid(), "rules": []},
        {**valid(), "rules": valid()["rules"] * 2},
        broken(id="T82"),
        broken(id="t1082"),
        broken(tactics=["Defense Evasion"]),
        broken(tactics=[]),
        broken(name=""),
        broken(reason=None),
        broken(patterns=[]),
        broken(patterns=["(a+)+"]),
        broken(patterns=["("]),
        broken(patterns=["a" * 600]),
        broken(patterns=[42]),
    ],
)
def test_a_broken_rule_file_is_refused(data):
    with pytest.raises(RulesError):
        parse_rules(data)


def test_a_rule_file_that_is_no_yaml_is_refused(tmp_path):
    path = tmp_path / "attack.yml"
    path.write_text("rules: [unclosed", encoding="utf-8")
    with pytest.raises(RulesError):
        load_rules(path)


def test_a_valid_rule_file_loads(tmp_path):
    path = tmp_path / "attack.yml"
    path.write_text(yaml.safe_dump(valid()), encoding="utf-8")
    assert load_rules(path).classify("uname -a") == ["T1082"]
