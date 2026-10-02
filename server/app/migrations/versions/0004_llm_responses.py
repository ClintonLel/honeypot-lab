"""Aufrufe in B und Abgleich mit den Befehlen

Neue Tabelle llm_responses: je Befehl in B ein Aufruf beim LLM-Gateway mit
Ausgang, HTTP-Status, Antwortzeit, Länge der Ausgabe und client_gone, aus
cowrie.llm.response (Patch für cowrie-b, Schritt 7.3, E-041, E-044). Bleibt,
wenn die Roh-Events nach 90 Tagen gelöscht werden.

commands bekommt input_ref, den HMAC über den SHA-256 des rohen Befehls.
Damit lässt sich prüfen, dass ein Aufruf zum Befehl an seiner Stelle gehört.
Ältere Befehle bleiben ohne Wert.

Revision: 0004
Vorher:   0003
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTCOMES = ("ok", "rate_limited", "unavailable", "upstream_error", "timeout", "local_rate_limit", "error")


def upgrade() -> None:
    op.add_column("commands", sa.Column("input_ref", sa.String(length=64), nullable=True))

    op.create_table(
        "llm_responses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("command_index", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("output_chars", sa.Integer(), nullable=False),
        sa.Column("client_gone", sa.Boolean(), nullable=False),
        sa.Column("input_ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "outcome IN (" + ", ".join(f"'{o}'" for o in OUTCOMES) + ")",
            name="ck_llm_responses_outcome",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "command_index", name="uq_llm_responses_session_index"),
    )
    op.create_index("ix_llm_responses_occurred_at", "llm_responses", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_responses_occurred_at", table_name="llm_responses")
    op.drop_table("llm_responses")
    op.drop_column("commands", "input_ref")
