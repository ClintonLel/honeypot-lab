"""Prüft das Schema gegen die harten Regeln des Projekts.

Der wichtigste Test hier ist ``test_no_column_can_hold_a_plaintext_ip``: Er
läuft über jede Spalte jeder Tabelle und lehnt alles ab, was nach einer
Adresse aussieht. Kommt später eine Tabelle dazu, schlägt er an, sobald jemand
eine IP-Spalte einbaut (E-009, E-022).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import CIDR, INET

from app.models import Base, VARIANTS

# Spaltennamen, die auf eine Adresse hindeuten. ip_hash ist ausdrücklich erlaubt.
IP_LIKE = re.compile(
    r"(^|_)(ip|ips|ipv4|ipv6|addr|address|src|source|dest|destination|remote|peer|host)"
    r"(_?(addr|address|ip))?($|_)",
    re.IGNORECASE,
)
ALLOWED = {"ip_hash"}

# Tabellen laut Bauplan, Schritt 3.3.
EXPECTED_TABLES = {
    "sessions",
    "events",
    "commands",
    "campaigns",
    "casts",
    "llm_usage",
    "daily_stats",
}


def all_columns():
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            yield table, column


def test_expected_tables_exist():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_no_column_can_hold_a_plaintext_ip():
    offenders = [
        f"{table.name}.{column.name}"
        for table, column in all_columns()
        if column.name not in ALLOWED and IP_LIKE.search(column.name)
    ]
    assert offenders == [], f"Spalten könnten eine Klartext-IP aufnehmen: {offenders}"


def test_no_column_uses_a_postgres_ip_type():
    offenders = [
        f"{table.name}.{column.name}"
        for table, column in all_columns()
        if isinstance(column.type, (INET, CIDR))
    ]
    assert offenders == []


def test_sessions_describe_origin_only_by_hash_and_enrichment():
    columns = Base.metadata.tables["sessions"].columns
    assert "ip_hash" in columns
    for name in ("country", "asn", "as_name"):
        assert name in columns
    assert columns["ip_hash"].type.length == 64


def test_varchar_columns_are_length_limited():
    """``Text`` ist für Befehle und Notizen gedacht, jedes ``VARCHAR`` ist begrenzt."""
    unlimited = [
        f"{table.name}.{column.name}"
        for table, column in all_columns()
        if isinstance(column.type, String)
        and not isinstance(column.type, Text)
        and column.type.length is None
    ]
    assert unlimited == []


@pytest.mark.parametrize("table_name", ["sessions", "events"])
def test_variant_is_restricted(table_name: str):
    table = Base.metadata.tables[table_name]
    checks = [c for c in table.constraints if c.name == f"ck_{table_name}_variant"]
    assert checks, f"{table_name} hat keine Prüfung auf die Variante"
    condition = str(checks[0].sqltext)
    for variant in VARIANTS:
        assert f"'{variant}'" in condition


def test_dedup_hash_is_unique():
    """Ohne diesen Index wäre der Ingest nicht idempotent (Schritt 4.1)."""
    events = Base.metadata.tables["events"]
    names = {c.name for c in events.constraints}
    assert "uq_events_dedup_hash" in names
