"""Gemini als Anbieter: Denk-Tokens, Weigerungen, Kosten in US-Dollar

Ergänzt llm_usage um reasoning_tokens (Teil der Ausgabe, den das Modell zum
Denken brauchte) und refusal (die Antwort passte zu einer Wendung aus
app.llm_refusal). Ab jetzt ist cost_micros in Millionstel US-Dollar statt
Euro (E-045).

Vorher prüft die Migration, dass in llm_usage noch keine Kosten stehen. Bis
E-045 wurde nie ein Key eines Anbieters eingetragen, jede Zeile hat 0 Kosten.
Gäbe es doch Zeilen mit Kosten, wären sie in Euro, und Monatssummen und
Budget mischten danach zwei Währungen. Dann bricht die Migration ab, statt
still weiterzumachen (server/README.md, „Ausrollen“).

Revision: 0005
Vorher:   0004
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class CostsInEuro(RuntimeError):
    """In llm_usage stehen schon Kosten, also in Euro."""


def upgrade() -> None:
    if not context.is_offline_mode():
        rows = op.get_bind().execute(sa.text("SELECT count(*) FROM llm_usage WHERE cost_micros > 0")).scalar_one()
        if rows:
            raise CostsInEuro(
                f"llm_usage hat {rows} Zeilen mit Kosten > 0 aus der Zeit vor E-045, also in Euro. "
                "Erst klären (server/README.md, Ausrollen), dann die Migration wiederholen."
            )
    op.add_column(
        "llm_usage",
        sa.Column("reasoning_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "llm_usage",
        sa.Column("refusal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("llm_usage", "refusal")
    op.drop_column("llm_usage", "reasoning_tokens")
