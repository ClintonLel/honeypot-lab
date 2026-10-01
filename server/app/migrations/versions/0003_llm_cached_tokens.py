"""Zwischengespeicherte Tokens in llm_usage

Ergänzt llm_usage um cached_tokens: der Teil von prompt_tokens, den der
Anbieter aus seinem Zwischenspeicher bedient und günstiger berechnet (E-015).
Gefüllt vom LLM-Gateway (Schritt 7.2, E-043).

Revision: 0003
Vorher:   0002
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_usage",
        sa.Column("cached_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("llm_usage", "cached_tokens")
