"""Abgleich der Aufrufe in B mit den Befehlen (Schritt 7.3, E-044).

Jeder Aufruf in ``llm_responses`` gehört zu der Zeile in ``commands``
derselben Sitzung mit ``sequence = command_index`` (method.md 7.1). Ob das
stimmt, zeigt ``input_ref``: Beide Seiten tragen den HMAC über den SHA-256
desselben rohen Befehls. Wurde ein ``command.input`` der Sitzung abgelehnt,
verschieben sich die Nummern, und der Abgleich schlägt an.

Gibt nur Zähler aus, nie Befehle oder Antworten:

    python -m app.llm_check            # alles
    python -m app.llm_check --tage 1   # nur die letzten 24 Stunden
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Connection, create_engine, text

# Je Aufruf: Gibt es den Befehl an seiner Stelle, und passt er?
RESPONSES_SQL = text(
    """
    SELECT
      count(*) AS aufrufe,
      count(*) FILTER (WHERE c.id IS NOT NULL AND c.input_ref = r.input_ref) AS passt,
      count(*) FILTER (WHERE c.id IS NOT NULL AND c.input_ref <> r.input_ref) AS passt_nicht,
      count(*) FILTER (WHERE c.id IS NULL) AS ohne_befehl,
      count(*) FILTER (WHERE c.id IS NOT NULL AND c.input_ref IS NULL) AS nicht_pruefbar
    FROM llm_responses r
    LEFT JOIN commands c ON c.session_id = r.session_id AND c.sequence = r.command_index
    WHERE r.occurred_at >= :seit
    """
)

# Je Befehl in B: Gibt es genau einen Aufruf? (Doppelte verhindert der
# eindeutige Index.) Kurz nach einem Befehl kann die Antwort noch unterwegs
# sein, deshalb erst Befehle, die älter als zwei Minuten sind.
COMMANDS_SQL = text(
    """
    SELECT count(*) AS befehle_ohne_aufruf
    FROM commands c
    JOIN sessions s ON s.id = c.session_id
    LEFT JOIN llm_responses r ON r.session_id = c.session_id AND r.command_index = c.sequence
    WHERE s.variant = 'b' AND r.id IS NULL
      AND c.occurred_at >= :seit AND c.occurred_at < :bis
    """
)

OUTCOMES_SQL = text(
    """
    SELECT outcome, count(*) AS n FROM llm_responses
    WHERE occurred_at >= :seit GROUP BY outcome ORDER BY outcome
    """
)


def counts(connection: Connection, since: datetime, now: datetime) -> dict[str, Any]:
    """Die Zähler des Abgleichs, ab ``since``."""
    params = {"seit": since}
    result: dict[str, Any] = dict(connection.execute(RESPONSES_SQL, params).mappings().one())
    result.update(
        connection.execute(
            COMMANDS_SQL, {"seit": since, "bis": now - timedelta(minutes=2)}
        ).mappings().one()
    )
    result["outcomes"] = {row.outcome: row.n for row in connection.execute(OUTCOMES_SQL, params)}
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.llm_check")
    parser.add_argument("--tage", type=float, default=None, help="nur die letzten N Tage")
    args = parser.parse_args(argv)

    from app.config import get_settings

    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(days=args.tage) if args.tage else datetime(2020, 1, 1, tzinfo=timezone.utc)
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as connection:
            result = counts(connection, since, now)
    finally:
        engine.dispose()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
