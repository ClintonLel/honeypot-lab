"""Abgleich der Aufrufe in B mit den Befehlen (Schritt 7.3, E-044).

Jeder Aufruf in ``llm_responses`` gehört zu der Zeile in ``commands``
derselben Sitzung mit ``sequence = command_index`` (method.md 7.1). Ob das
stimmt, zeigt ``input_ref``: Beide Seiten tragen den HMAC über den SHA-256
desselben rohen Befehls. Wurde ein ``command.input`` der Sitzung abgelehnt,
verschieben sich die Nummern, und der Abgleich schlägt an.

Dazu unter ``gateway`` die Sicht des Gateways aus ``llm_usage`` (E-045): Zahl
je Status, darunter gesperrte Antworten (``upstream_blocked``), die auf dem
Sensor nur als ``upstream_error`` erscheinen; Weigerungen laut
``app.llm_refusal``; die Cache-Quote (Summe ``cached_tokens`` / Summe
``prompt_tokens``) und die Kosten im Zeitraum, hochgerechnet auf einen Monat.
Die gebuchten Kosten enthalten die beobachtete Cache-Quote schon.

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

USAGE_STATUS_SQL = text(
    """
    SELECT status, count(*) AS n FROM llm_usage
    WHERE occurred_at >= :seit GROUP BY status ORDER BY status
    """
)

# Aufrufe beim Anbieter haben eine Latenz; nur sie haben Tokens und Kosten.
USAGE_SUMS_SQL = text(
    """
    SELECT
      count(*) FILTER (WHERE latency_ms IS NOT NULL) AS anbieter,
      count(*) FILTER (WHERE refusal) AS weigerungen,
      coalesce(sum(cached_tokens), 0) AS cached,
      coalesce(sum(prompt_tokens), 0) AS prompt,
      coalesce(sum(cost_micros), 0) AS kosten,
      min(occurred_at) AS erste
    FROM llm_usage
    WHERE occurred_at >= :seit
    """
)

DAYS_PER_MONTH = 30.4


def gateway_counts(
    connection: Connection, since: datetime, now: datetime, days: float | None = None
) -> dict[str, Any]:
    """Status, Weigerungen, Cache-Quote und Kosten aus ``llm_usage``.

    ``days`` ist die Länge des Zeitraums; ohne Angabe zählt er ab der ersten
    Zeile. Kosten in US-Dollar (E-045).
    """
    params = {"seit": since}
    status = {row.status: row.n for row in connection.execute(USAGE_STATUS_SQL, params)}
    sums = connection.execute(USAGE_SUMS_SQL, params).mappings().one()
    if days is None:
        days = (now - sums["erste"]).total_seconds() / 86_400 if sums["erste"] else 0.0
    cost = int(sums["kosten"]) / 1_000_000
    per_day = sums["anbieter"] / days if days > 0 else None
    return {
        "status": status,
        "weigerungen": sums["weigerungen"],
        "cache_quote": round(int(sums["cached"]) / int(sums["prompt"]), 4) if sums["prompt"] else None,
        "kosten_usd": round(cost, 6),
        "tage": round(days, 3),
        "aufrufe_je_tag": round(per_day, 1) if per_day is not None else None,
        "kosten_je_monat_usd": round(cost / days * DAYS_PER_MONTH, 2) if days > 0 else None,
    }


def counts(
    connection: Connection, since: datetime, now: datetime, days: float | None = None
) -> dict[str, Any]:
    """Die Zähler des Abgleichs, ab ``since``."""
    params = {"seit": since}
    result: dict[str, Any] = dict(connection.execute(RESPONSES_SQL, params).mappings().one())
    result.update(
        connection.execute(
            COMMANDS_SQL, {"seit": since, "bis": now - timedelta(minutes=2)}
        ).mappings().one()
    )
    result["outcomes"] = {row.outcome: row.n for row in connection.execute(OUTCOMES_SQL, params)}
    result["gateway"] = gateway_counts(connection, since, now, days)
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
            result = counts(connection, since, now, args.tage or None)
    finally:
        engine.dispose()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
