"""Prüft Einstellungen und den Umgang mit Secrets."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import PLACEHOLDER, Settings

SECRET = "s" * 64


def production(**overrides) -> Settings:
    values = {
        "environment": "production",
        "postgres_password": SECRET,
        "ip_hmac_key": SECRET,
        "ingest_token": SECRET,
    }
    values.update(overrides)
    return Settings(**values)


def test_secrets_never_appear_in_repr_or_str(settings: Settings):
    text = f"{settings!r} {settings}"
    assert "t" * 64 not in text
    assert "**********" in text


def test_database_url_is_built_from_the_parts(settings: Settings):
    url = settings.database_url
    assert url.startswith("postgresql+psycopg://")
    assert "@db:5432/honeypot" in url


def test_database_url_escapes_special_characters():
    settings = production(postgres_password="a/b@c:" + "x" * 58)
    assert "a%2Fb%40c%3A" in settings.database_url


def test_production_rejects_the_placeholder():
    with pytest.raises(ValidationError, match="IP_HMAC_KEY"):
        production(ip_hmac_key=PLACEHOLDER)


def test_production_rejects_short_secrets():
    with pytest.raises(ValidationError, match="INGEST_TOKEN"):
        production(ingest_token="zu-kurz")


def test_production_rejects_missing_secrets():
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        production(postgres_password="")


def test_tests_and_development_may_run_without_secrets(monkeypatch):
    """Außerhalb von production darf ein Secret fehlen.

    Erst die Umgebung leeren, sonst prüft der Test die Werte des Rechners, auf
    dem er läuft. Verglichen wird ein Wahrheitswert, nie der Wert selbst: Sonst
    stünde bei einem Fehlschlag das Secret in der pytest-Ausgabe.
    """
    for name in ("POSTGRES_PASSWORD", "IP_HMAC_KEY", "INGEST_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(environment="test")
    has_key = bool(settings.ip_hmac_key.get_secret_value())
    assert has_key is False


def test_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("POSTGRES_HOST", "anderer-host")
    settings = Settings(environment="test")
    assert settings.log_level == "DEBUG"
    assert settings.postgres_host == "anderer-host"
