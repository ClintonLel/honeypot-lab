"""Kennzahlen für Kampagnen

Ergänzt campaigns um sources (verschiedene ip_hash), asns (verschiedene ASN)
und median_interval_s (Median der Abstände zwischen aufeinanderfolgenden
Sitzungsstarts). Gefüllt vom Worker-Job campaigns (Schritt 6.2, E-039).

Revision: 0002
Vorher:   0001
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("sources", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "campaigns",
        sa.Column("asns", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("campaigns", sa.Column("median_interval_s", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "median_interval_s")
    op.drop_column("campaigns", "asns")
    op.drop_column("campaigns", "sources")
