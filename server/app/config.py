"""Einstellungen der Lab-API.

Alle Werte kommen aus Umgebungsvariablen, nichts steht im Code. Secrets sind
``SecretStr``: Sie tauchen damit weder in ``repr`` noch in Logs oder
Fehlermeldungen auf (E-009, AGENTS.md „Harte Regeln“).
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Platzhalter aus .env.example. Wer sie im Betrieb stehen lässt, soll einen
# Fehler beim Start bekommen und keinen Honeypot mit Beispielschlüssel.
PLACEHOLDER = "CHANGE_ME"

# 32 Byte als Hex sind 64 Zeichen. Kürzere Schlüssel lassen wir nicht zu,
# weil der Hash sonst ratbar wird (E-009).
MIN_SECRET_LENGTH = 32


def secret_problem(value: str) -> str | None:
    """Was an einem Secret nicht stimmt, ohne den Wert zu nennen.

    ``None`` heißt: brauchbar. Gilt für die Pflicht-Secrets beim Start und für
    die Secrets des LLM-Gateways (E-023, E-043).
    """
    if not value or value == PLACEHOLDER:
        return "fehlt oder ist noch der Platzhalter"
    if len(value) < MIN_SECRET_LENGTH:
        return f"ist zu kurz, mindestens {MIN_SECRET_LENGTH} Zeichen"
    return None


# Felder des LLM-Gateways, die beim Lesen nachsichtig sind (siehe unten).
_LLM_LENIENT = (
    "llm_max_tokens",
    "llm_temperature",
    "llm_timeout_seconds",
    "llm_budget_month_usd",
    "llm_budget_day_usd",
    "llm_calls_per_minute",
)


class Settings(BaseSettings):
    """Konfiguration der API und des Workers."""

    model_config = SettingsConfigDict(
        # Die .env liest Docker Compose, nicht die Anwendung. So landet die
        # Datei nie im Image und der Container bekommt nur, was er braucht.
        env_file=None,
        extra="ignore",
        frozen=True,
    )

    environment: str = "production"
    log_level: str = "INFO"

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "honeypot"
    postgres_user: str = "honeypot"
    postgres_password: SecretStr = SecretStr("")

    # Schlüssel für den HMAC der Quell-IPs. Fest über die gesamte Laufzeit,
    # siehe E-022.
    ip_hmac_key: SecretStr = SecretStr("")

    # Bearer-Token, mit dem der Sensor Events einliefert (Schritt 4.1).
    ingest_token: SecretStr = SecretStr("")

    ipinfo_token: SecretStr = SecretStr("")

    # LLM-Gateway (Schritt 7.2, E-043, Anbieter Gemini seit E-045). Keiner
    # dieser Werte darf den Start verhindern, Ingest und Statistik laufen auch
    # ohne Gateway. Was sich nicht lesen lässt, wird zu None; leer heißt
    # Vorgabe. Wertebereiche prüft das Gateway selbst und antwortet mit 503,
    # solange etwas nicht stimmt. Adresse und Preise des Anbieters stehen fest
    # in app/llm_provider.py, nicht hier.
    llm_api_key: SecretStr = SecretStr("")
    llm_gateway_token: SecretStr = SecretStr("")
    llm_gateway_enabled: bool = False
    # Eine Modell-ID aus app.llm_provider.MODELS.
    llm_model: str = ""
    llm_max_tokens: int | None = 2048
    # Googles Vorgabe für Gemini 3; darunter drohen Schleifen (E-045).
    llm_temperature: float | None = 1.0
    llm_timeout_seconds: float | None = 30.0
    # So wenig Denken wie das Modell erlaubt (E-045).
    llm_reasoning_effort: str = "minimal"
    # Aufeinanderfolgende Nachrichten derselben Rolle zusammenfassen, falls
    # Gemini sie ablehnt (Probe "verlauf", server/README.md).
    llm_merge_turns: bool = False
    # US-Dollar. Ohne Vorgabe: Wer keine Budgets einträgt, bekommt kein Gateway.
    llm_budget_month_usd: Decimal | None = None
    llm_budget_day_usd: Decimal | None = None
    llm_calls_per_minute: int | None = 60
    # SHA-256 des Persona-Teils im System-Prompt. Leer heißt: nicht gepinnt.
    llm_prompt_sha256: str = ""

    # Pfad zur IPinfo-Lite-Datenbank. Der Worker legt sie dort ab
    # (Schritt 4.3), die API liest sie nur.
    ipinfo_db_path: str = "/data/ipinfo.mmdb"

    # Nach so vielen Tagen löscht der Worker Roh-Events. Sitzungen, Befehle
    # und die Tagesstatistik bleiben (Schritt 4.3).
    raw_event_retention_days: int = Field(default=90, ge=7)

    # Nur für Tests und lokale Läufe interessant.
    sql_echo: bool = Field(default=False)

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator(*_LLM_LENIENT, mode="wrap")
    @classmethod
    def _lenient_number(
        cls, value: Any, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> Any:
        """Leer wird zur Vorgabe, Unlesbares zu None, nie ein Fehler beim Start."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return cls.model_fields[info.field_name].default
        try:
            return handler(value)
        except ValidationError:
            return None

    @field_validator("llm_reasoning_effort", mode="before")
    @classmethod
    def _default_effort(cls, value: Any) -> Any:
        """Leer heißt Vorgabe, wie bei den Zahlen."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return cls.model_fields["llm_reasoning_effort"].default
        return value

    @field_validator("llm_gateway_enabled", "llm_merge_turns", mode="wrap")
    @classmethod
    def _lenient_switch(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> bool:
        """Ein unlesbarer Schalter gilt als aus."""
        try:
            return handler(value)
        except ValidationError:
            return False

    @model_validator(mode="after")
    def _require_secrets_in_production(self) -> Settings:
        if self.environment != "production":
            return self
        required = {
            "POSTGRES_PASSWORD": self.postgres_password,
            "IP_HMAC_KEY": self.ip_hmac_key,
            "INGEST_TOKEN": self.ingest_token,
        }
        for name, secret in required.items():
            problem = secret_problem(secret.get_secret_value())
            if problem:
                raise ValueError(f"{name} {problem}")
        return self

    @property
    def database_url(self) -> str:
        """DSN für SQLAlchemy. Enthält das Passwort, gehört nicht in Logs."""
        password = quote(self.postgres_password.get_secret_value(), safe="")
        user = quote(self.postgres_user, safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def ip_hmac_key_bytes(self) -> bytes:
        return self.ip_hmac_key.get_secret_value().encode("utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Einmal lesen, danach aus dem Cache. Tests leeren ihn per ``cache_clear``."""
    return Settings()
