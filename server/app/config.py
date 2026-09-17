"""Einstellungen der Lab-API.

Alle Werte kommen aus Umgebungsvariablen, nichts steht im Code. Secrets sind
``SecretStr``: Sie tauchen damit weder in ``repr`` noch in Logs oder
Fehlermeldungen auf (E-009, README „Harte Regeln“).
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Platzhalter aus .env.example. Wer sie im Betrieb stehen lässt, soll einen
# Fehler beim Start bekommen und keinen Honeypot mit Beispielschlüssel.
PLACEHOLDER = "CHANGE_ME"

# 32 Byte als Hex sind 64 Zeichen. Kürzere Schlüssel lassen wir nicht zu,
# weil der Hash sonst ratbar wird (E-009).
MIN_SECRET_LENGTH = 32


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

    # Erst ab Phase 7 nötig, deshalb ohne Prüfung beim Start.
    llm_api_key: SecretStr = SecretStr("")
    llm_gateway_token: SecretStr = SecretStr("")
    ipinfo_token: SecretStr = SecretStr("")

    # Pfad zur IPinfo-Lite-Datenbank. Der Worker legt sie dort ab
    # (Schritt 4.3), die API liest sie nur.
    ipinfo_db_path: str = "/data/ipinfo.mmdb"

    # Nur für Tests und lokale Läufe interessant.
    sql_echo: bool = Field(default=False)

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

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
            value = secret.get_secret_value()
            if not value or value == PLACEHOLDER:
                raise ValueError(f"{name} fehlt oder ist noch der Platzhalter")
            if len(value) < MIN_SECRET_LENGTH:
                raise ValueError(f"{name} ist zu kurz, mindestens {MIN_SECRET_LENGTH} Zeichen")
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
