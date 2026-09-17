"""Prüft das Entschärfen von URLs und Adressen (README „Harte Regeln“)."""

from __future__ import annotations

import pytest

from app.defang import defang, shorten


@pytest.mark.parametrize(
    "text, expected",
    [
        ("wget http://45.9.148.99/x.sh", "wget hxxp://45[.]9[.]148[.]99/x.sh"),
        ("curl https://beispiel.test/a.bin", "curl hxxps://beispiel[.]test/a.bin"),
        ("ftp://dateien.beispiel.test/x", "fxp://dateien[.]beispiel[.]test/x"),
        ("tftp://10.0.0.9/boot", "tfxp://10[.]0[.]0[.]9/boot"),
    ],
)
def test_urls_lose_their_scheme_and_dots(text: str, expected: str):
    assert defang(text) == expected


def test_the_path_stays_readable():
    """Nur der Namensteil wird entschärft, sonst liest sich nichts mehr."""
    assert defang("http://beispiel.test/pfad/datei.sh") == "hxxp://beispiel[.]test/pfad/datei.sh"


def test_bare_addresses_are_defanged_too():
    assert defang("verbinde zu 8.8.8.8 und 203.0.113.5") == "verbinde zu 8[.]8[.]8[.]8 und 203[.]0[.]113[.]5"


def test_an_address_inside_a_url_is_only_defanged_once():
    assert defang("http://1.2.3.4:8080/a") == "hxxp://1[.]2[.]3[.]4:8080/a"


def test_uppercase_schemes_are_caught():
    assert defang("HTTP://Beispiel.test/x").startswith("hxxp://")


def test_harmless_text_stays_as_it_is():
    for text in ("uname -a", "OpenSSH_10.0p2 Debian-7", "cat /etc/os-release", ""):
        assert defang(text) == text


def test_version_numbers_are_not_addresses():
    """Vier Zahlen mit Punkten wären eine Adresse, drei nicht."""
    assert defang("Debian 6.12.107") == "Debian 6.12.107"


def test_shorten_marks_the_cut():
    assert shorten("abcdef", 4) == "abc…"
    assert shorten("abc", 4) == "abc"
