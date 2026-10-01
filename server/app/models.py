"""Datenbankmodelle des Labs (SQLAlchemy 2).

Grundregel aus E-009 und E-022: In keiner Tabelle steht eine Klartext-IP. Die
Herkunft einer Sitzung wird ausschließlich über ``ip_hash`` (HMAC-SHA256),
``country``, ``asn`` und ``as_name`` beschrieben. ``server/tests/test_schema.py``
prüft das für jede Spalte, damit es auch in Zukunft so bleibt.

Längen sind überall begrenzt, weil fast jeder Wert hier aus einer feindlichen
Quelle stammt (AGENTS.md „Harte Regeln“).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Varianten des Experiments: a ist die klassische Shell, b die KI-Shell (E-002).
VARIANTS = ("a", "b")

# Länge eines Hex-SHA256.
HASH_LENGTH = 64


class Base(DeclarativeBase):
    """Gemeinsame Basis. ``dict``- und ``list``-Felder werden zu ``jsonb``."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


def _variant_check(table: str) -> CheckConstraint:
    values = ", ".join(f"'{v}'" for v in VARIANTS)
    return CheckConstraint(f"variant IN ({values})", name=f"ck_{table}_variant")


class Campaign(Base):
    """Eine Gruppe von Sitzungen mit gleichem Fingerprint (Schritt 6.2)."""

    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_campaigns_fingerprint"),
        CheckConstraint("kind IN ('exec', 'interactive')", name="ck_campaigns_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(HASH_LENGTH))
    kind: Mapped[str] = mapped_column(String(16))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sessions_a: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    sessions_b: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # {"DE": 12, "CN": 4}
    countries: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    # ["T1105", "T1496"]
    techniques: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    # Verschiedene ip_hash und ASNs, nur als Anzahl (Migration 0002).
    sources: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    asns: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Median der Abstände zwischen aufeinanderfolgenden Sitzungsstarts.
    median_interval_s: Mapped[int | None] = mapped_column(Integer)
    # Nur aus rules/campaigns.yml, nie von Hand per SQL (docs/campaigns.md).
    label: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="campaign")


class Session(Base):
    """Eine SSH-Sitzung auf einem der beiden Honeypots."""

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("cowrie_session", name="uq_sessions_cowrie_session"),
        _variant_check("sessions"),
        Index("ix_sessions_started_at", "started_at"),
        Index("ix_sessions_ip_hash", "ip_hash"),
        Index("ix_sessions_campaign_id", "campaign_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Sitzungs-ID von Cowrie, z.B. "a1b2c3d4e5f6".
    cowrie_session: Mapped[str] = mapped_column(String(64))
    variant: Mapped[str] = mapped_column(String(1))
    sensor_name: Mapped[str] = mapped_column(String(32))

    # Herkunft: nur Hash und Anreicherung, nie die Adresse selbst (E-009).
    ip_hash: Mapped[str] = mapped_column(String(HASH_LENGTH))
    country: Mapped[str | None] = mapped_column(String(2))
    asn: Mapped[str | None] = mapped_column(String(16))
    as_name: Mapped[str | None] = mapped_column(String(128))

    # Fingerabdruck des Clients, aus cowrie.client.version und .kex.
    client_version: Mapped[str | None] = mapped_column(String(128))
    hassh: Mapped[str | None] = mapped_column(String(32))

    # Zugangsdaten, die der Angreifer probiert hat. Das ist seine Eingabe,
    # kein fremdes Geheimnis, und für die Auswertung interessant.
    login_username: Mapped[str | None] = mapped_column(String(128))
    login_password: Mapped[str | None] = mapped_column(String(128))

    # None, solange die Sitzung noch nicht klassifiziert ist (Schritt 4.1).
    interactive: Mapped[bool | None] = mapped_column(Boolean)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    command_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    campaign: Mapped[Campaign | None] = relationship(back_populates="sessions")
    commands: Mapped[list["Command"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Event(Base):
    """Ein Roh-Event aus cowrie.json, unverändert als ``jsonb``.

    ``dedup_hash`` macht den Ingest idempotent: Liefert Vector nach einem
    Neustart dieselbe Zeile erneut, greift der eindeutige Index (Schritt 4.1).
    Roh-Events werden nach 90 Tagen gelöscht (Schritt 4.3).
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_events_dedup_hash"),
        _variant_check("events"),
        Index("ix_events_occurred_at", "occurred_at"),
        Index("ix_events_eventid", "eventid"),
        Index("ix_events_session_id", "session_id"),
        Index("ix_events_cowrie_session", "cowrie_session"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dedup_hash: Mapped[str] = mapped_column(String(HASH_LENGTH))
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    # Die Roh-ID aus dem Event, auch wenn die Sitzung noch nicht angelegt ist.
    cowrie_session: Mapped[str | None] = mapped_column(String(64))
    eventid: Mapped[str] = mapped_column(String(64))
    variant: Mapped[str] = mapped_column(String(1))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Der Klartext der IP wird vor dem Speichern aus dem Payload entfernt.
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Command(Base):
    """Ein Befehl aus einer Sitzung, entschärft für die Anzeige."""

    __tablename__ = "commands"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_commands_session_sequence"),
        Index("ix_commands_occurred_at", "occurred_at"),
        Index("ix_commands_command_hash", "command_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    # Reihenfolge innerhalb der Sitzung, beginnt bei 1.
    sequence: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Bereits entschärft: hxxp:// statt http://, [.] statt Punkt in IPs.
    command: Mapped[str] = mapped_column(Text)
    # Hash des normalisierten Befehls, Grundlage der Kampagnen (Schritt 6.2).
    command_hash: Mapped[str] = mapped_column(String(HASH_LENGTH))
    # ATT&CK-Techniken, wird in Schritt 6.1 gefüllt: ["T1105", "T1082"]
    techniques: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[Session] = relationship(back_populates="commands")


class Cast(Base):
    """Ein Sitzungsmitschnitt im asciinema-Format (Schritt 6.3)."""

    __tablename__ = "casts"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_casts_session_id"),
        UniqueConstraint("sha256", name="uq_casts_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    sha256: Mapped[str] = mapped_column(String(HASH_LENGTH))
    duration_ms: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Nur die entschärfte Fassung wird gespeichert.
    frames: Mapped[list[Any]] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LlmUsage(Base):
    """Eine Anfrage mit gültigem Token an das LLM-Gateway (Schritt 7.2, E-043).

    Kein Inhalt: weder Prompt noch Antwort, nur Zahlen. Cowrie schickt weder
    Adresse noch Sitzung mit, ``session_id`` bleibt deshalb leer (E-041).
    """

    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_occurred_at", "occurred_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Teil von prompt_tokens aus dem Zwischenspeicher des Anbieters (Migration 0003).
    cached_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Kosten in Millionstel Euro, damit nichts gerundet werden muss. Bei
    # "timeout" und fehlendem usage eine obere Schätzung (E-043).
    cost_micros: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    # Dauer des Aufrufs beim Anbieter. Leer, wenn er nicht gerufen wurde.
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # ok, rate_limited, budget_exceeded, timeout, upstream_error, rejected, disabled
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DailyStat(Base):
    """Tagesaggregate für die Seite /lab (Schritte 4.3 und 5.1).

    Bewusst schmal gehalten: ``(tag, variante, metrik, dimension) -> wert``.
    Damit passen Übersicht, Länderverteilung und Heatmap in dieselbe Tabelle,
    ohne dass für jede neue Kennzahl eine Migration nötig ist. ``dimension``
    ist "" statt NULL, weil NULL in einem Primärschlüssel nicht erlaubt ist.
    """

    __tablename__ = "daily_stats"
    __table_args__ = (
        CheckConstraint("variant IN ('a', 'b', 'all')", name="ck_daily_stats_variant"),
    )

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    variant: Mapped[str] = mapped_column(String(3), primary_key=True)
    # z.B. "sessions", "commands", "sessions_by_country", "sessions_by_hour"
    metric: Mapped[str] = mapped_column(String(48), primary_key=True)
    # z.B. "" oder "DE" oder "14" (Stunde)
    dimension: Mapped[str] = mapped_column(String(48), primary_key=True, server_default=text("''"))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    # Wie viele Einzelwerte hinter dem Wert stehen, für Konfidenzintervalle.
    sample_size: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
