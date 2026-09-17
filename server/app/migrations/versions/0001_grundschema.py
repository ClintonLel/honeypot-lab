"""Grundschema des Labs

Legt die sieben Tabellen aus Schritt 3.3 an: campaigns, sessions, events,
commands, casts, llm_usage und daily_stats. Klartext-IPs kommen in keiner
Tabelle vor, nur ``ip_hash``, ``country``, ``asn`` und ``as_name`` (E-009).

Revision: 0001
Vorher:   -
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessions_a", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sessions_b", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "countries",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "techniques",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("kind IN ('exec', 'interactive')", name="ck_campaigns_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_campaigns_fingerprint"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cowrie_session", sa.String(length=64), nullable=False),
        sa.Column("variant", sa.String(length=1), nullable=False),
        sa.Column("sensor_name", sa.String(length=32), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("asn", sa.String(length=16), nullable=True),
        sa.Column("as_name", sa.String(length=128), nullable=True),
        sa.Column("client_version", sa.String(length=128), nullable=True),
        sa.Column("hassh", sa.String(length=32), nullable=True),
        sa.Column("login_username", sa.String(length=128), nullable=True),
        sa.Column("login_password", sa.String(length=128), nullable=True),
        sa.Column("interactive", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("command_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("variant IN ('a', 'b')", name="ck_sessions_variant"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cowrie_session", name="uq_sessions_cowrie_session"),
    )
    op.create_index("ix_sessions_campaign_id", "sessions", ["campaign_id"], unique=False)
    op.create_index("ix_sessions_ip_hash", "sessions", ["ip_hash"], unique=False)
    op.create_index("ix_sessions_started_at", "sessions", ["started_at"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("cowrie_session", sa.String(length=64), nullable=True),
        sa.Column("eventid", sa.String(length=64), nullable=False),
        sa.Column("variant", sa.String(length=1), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("variant IN ('a', 'b')", name="ck_events_variant"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash", name="uq_events_dedup_hash"),
    )
    op.create_index("ix_events_cowrie_session", "events", ["cowrie_session"], unique=False)
    op.create_index("ix_events_eventid", "events", ["eventid"], unique=False)
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"], unique=False)
    op.create_index("ix_events_session_id", "events", ["session_id"], unique=False)

    op.create_table(
        "commands",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "techniques",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_commands_session_sequence"),
    )
    op.create_index("ix_commands_command_hash", "commands", ["command_hash"], unique=False)
    op.create_index("ix_commands_occurred_at", "commands", ["occurred_at"], unique=False)

    op.create_table(
        "casts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("frames", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_casts_session_id"),
        sa.UniqueConstraint("sha256", name="uq_casts_sha256"),
    )

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_occurred_at", "llm_usage", ["occurred_at"], unique=False)

    op.create_table(
        "daily_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("variant", sa.String(length=3), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("dimension", sa.String(length=48), server_default=sa.text("''"), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("sample_size", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("variant IN ('a', 'b', 'all')", name="ck_daily_stats_variant"),
        sa.PrimaryKeyConstraint("day", "variant", "metric", "dimension"),
    )


def downgrade() -> None:
    op.drop_table("daily_stats")
    op.drop_index("ix_llm_usage_occurred_at", table_name="llm_usage")
    op.drop_table("llm_usage")
    op.drop_table("casts")
    op.drop_index("ix_commands_occurred_at", table_name="commands")
    op.drop_index("ix_commands_command_hash", table_name="commands")
    op.drop_table("commands")
    op.drop_index("ix_events_session_id", table_name="events")
    op.drop_index("ix_events_occurred_at", table_name="events")
    op.drop_index("ix_events_eventid", table_name="events")
    op.drop_index("ix_events_cowrie_session", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_sessions_started_at", table_name="sessions")
    op.drop_index("ix_sessions_ip_hash", table_name="sessions")
    op.drop_index("ix_sessions_campaign_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("campaigns")
