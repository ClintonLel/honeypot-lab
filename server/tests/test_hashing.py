"""Prüft den HMAC der Quell-IPs (E-009, E-022)."""

from __future__ import annotations

import pytest

from app.hashing import InvalidAddress, hash_ip, normalize_ip

KEY = b"k" * 64
OTHER_KEY = b"m" * 64

# Adressen aus dem Dokumentationsbereich, nie echte Angreifer-IPs.
IPV4 = "203.0.113.7"
IPV6 = "2001:db8::1"


def test_same_address_gives_the_same_hash():
    assert hash_ip(IPV4, KEY) == hash_ip(IPV4, KEY)


def test_different_addresses_give_different_hashes():
    assert hash_ip(IPV4, KEY) != hash_ip("203.0.113.8", KEY)


def test_a_different_key_makes_hashes_incomparable():
    """Genau deshalb rotiert der Schlüssel nicht (E-022)."""
    assert hash_ip(IPV4, KEY) != hash_ip(IPV4, OTHER_KEY)


def test_hash_is_hex_sha256():
    value = hash_ip(IPV4, KEY)
    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")


def test_hash_does_not_contain_the_address():
    assert IPV4 not in hash_ip(IPV4, KEY)


@pytest.mark.parametrize(
    "written, expected",
    [
        ("2001:DB8::0:1", "2001:db8::1"),
        ("2001:db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        ("  203.0.113.7  ", "203.0.113.7"),
    ],
)
def test_addresses_are_normalized(written: str, expected: str):
    assert normalize_ip(written) == expected


def test_notation_does_not_change_the_hash():
    assert hash_ip("2001:DB8::0:1", KEY) == hash_ip(IPV6, KEY)


def test_invalid_input_raises_without_echoing_it():
    with pytest.raises(InvalidAddress) as exc:
        hash_ip("nicht-wirklich-eine-ip", KEY)
    assert "nicht-wirklich-eine-ip" not in str(exc.value)


def test_empty_key_is_refused():
    with pytest.raises(ValueError, match="IP_HMAC_KEY"):
        hash_ip(IPV4, b"")
