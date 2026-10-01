"""Prüft Einstellungen und den Umgang mit Secrets."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import PLACEHOLDER, Settings, secret_problem

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


# --- LLM-Gateway (Schritt 7.2) -------------------------------------------------


def test_secret_problem_names_the_problem_but_not_the_value():
    assert secret_problem("") == "fehlt oder ist noch der Platzhalter"
    assert secret_problem(PLACEHOLDER) == "fehlt oder ist noch der Platzhalter"
    assert "zu kurz" in secret_problem("kurz-und-geheim")
    assert "kurz-und-geheim" not in secret_problem("kurz-und-geheim")
    assert secret_problem(SECRET) is None


def test_broken_llm_values_never_stop_the_start():
    """Ingest und Statistik dürfen nicht am Gateway hängen (E-043)."""
    settings = production(
        llm_api_key="",
        llm_gateway_token=PLACEHOLDER,
        llm_gateway_enabled="vielleicht",
        llm_max_tokens="viele",
        llm_temperature="warm",
        llm_timeout_seconds="-",
        llm_price_input_eur="0,15",
        llm_budget_month_eur="zwanzig",
        llm_calls_per_minute="1.5",
    )
    assert settings.llm_gateway_enabled is False
    assert settings.llm_max_tokens is None
    assert settings.llm_temperature is None
    assert settings.llm_timeout_seconds is None
    assert settings.llm_price_input_eur is None
    assert settings.llm_budget_month_eur is None
    assert settings.llm_calls_per_minute is None


def test_empty_llm_values_fall_back_to_the_defaults(monkeypatch):
    """Compose reicht fehlende Variablen als leeren String durch."""
    for name in ("LLM_MAX_TOKENS", "LLM_TEMPERATURE", "LLM_TIMEOUT_SECONDS", "LLM_CALLS_PER_MINUTE",
                 "LLM_PRICE_INPUT_EUR", "LLM_BUDGET_DAY_EUR"):
        monkeypatch.setenv(name, "")
    settings = Settings(environment="test")
    assert settings.llm_max_tokens == 2048
    assert settings.llm_temperature == 0.0
    assert settings.llm_timeout_seconds == 30.0
    assert settings.llm_calls_per_minute == 60
    assert settings.llm_price_input_eur is None
    assert settings.llm_budget_day_eur is None


def test_llm_values_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("LLM_PRICE_CACHED_INPUT_EUR", "0.075")
    monkeypatch.setenv("LLM_BUDGET_MONTH_EUR", "25")
    settings = Settings(environment="test")
    assert settings.llm_gateway_enabled is True
    assert settings.llm_price_cached_input_eur == Decimal("0.075")
    assert settings.llm_budget_month_eur == Decimal("25")


def test_llm_secrets_never_appear_in_repr():
    settings = production(llm_api_key="a" * 64, llm_gateway_token="b" * 64)
    text = f"{settings!r} {settings}"
    assert "a" * 64 not in text
    assert "b" * 64 not in text
