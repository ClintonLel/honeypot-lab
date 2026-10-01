"""Bearer-Prüfung für /ingest und das LLM-Gateway (app/auth.py)."""

from __future__ import annotations

from fastapi.security import HTTPAuthorizationCredentials

from app.auth import rejection_fields, token_matches

EXPECTED = "e" * 64


def bearer(value: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=value)


def test_the_right_token_matches():
    assert token_matches(bearer(EXPECTED), EXPECTED) is True


def test_a_wrong_or_missing_token_does_not_match():
    assert token_matches(bearer("f" * 64), EXPECTED) is False
    assert token_matches(None, EXPECTED) is False


def test_nothing_matches_when_no_token_is_configured():
    assert token_matches(bearer(""), "") is False
    assert token_matches(None, "") is False


def test_non_ascii_tokens_are_refused_instead_of_crashing():
    """compare_digest wirft bei Nicht-ASCII-Strings; der Header kommt vom Absender."""
    assert token_matches(bearer("ÿ" * 64), EXPECTED) is False
    assert token_matches(bearer("ä"), EXPECTED) is False


def test_the_log_fields_describe_the_header_without_the_value():
    fields = rejection_fields(bearer("${LLM_GATEWAY_TOKEN}"), EXPECTED)
    assert fields == {
        "scheme": "Bearer",
        "laenge": 20,
        "erwartete_laenge": 64,
        "sieht_aus_wie_platzhalter": True,
    }
    assert EXPECTED not in str(rejection_fields(bearer(EXPECTED), EXPECTED))
