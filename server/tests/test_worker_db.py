"""Statistik und Aufräumen gegen eine echte Datenbank (Marker ``db``).

Die echten Beispiel-Ereignisse vom Sensor laufen über die API in die
Testdatenbank. Danach rechnet der Worker die Tagesstatistik und räumt auf.
Die Erwartungen werden aus den Fixtures selbst abgeleitet, nicht von Hand
eingetragen.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select, text

from app.models import Command, DailyStat, Event, Session
from tests.conftest import make_ctx, run, send
from worker import jobs

pytestmark = pytest.mark.db

DAY = date(2026, 9, 17)
NEXT_DAY = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
MUCH_LATER = datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ingested(client, cowrie_events):
    response = send(client, cowrie_events)
    assert response.json()["rejected"] == 0
    return cowrie_events


def stat(engine, metric: str, variant: str = "a", dimension: str = "", day: date = DAY):
    with engine.connect() as connection:
        value = connection.execute(
            select(DailyStat.value).where(
                DailyStat.day == day,
                DailyStat.variant == variant,
                DailyStat.metric == metric,
                DailyStat.dimension == dimension,
            )
        ).scalar()
    return None if value is None else int(value)


def scalar(engine, statement):
    with engine.connect() as connection:
        return connection.execute(statement).scalar()


# --- Tagesstatistik ---------------------------------------------------------


def test_the_statistics_match_the_sessions(ingested, migrated, database_url):
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))

    sessions = {e["session"] for e in ingested}
    logins = {e["session"] for e in ingested if e["eventid"] == "cowrie.login.success"}
    with_pty = {e["session"] for e in ingested if e["eventid"] == "cowrie.client.size"}
    with_commands = {e["session"] for e in ingested if e["eventid"] == "cowrie.command.input"}
    sources = {e["src_ip"] for e in ingested if e.get("src_ip")}
    commands = sum(1 for e in ingested if e["eventid"] == "cowrie.command.input")

    assert stat(migrated, "sessions") == len(sessions)
    assert stat(migrated, "logins") == len(logins)
    assert stat(migrated, "sessions_interactive") == len(with_pty)
    assert stat(migrated, "sessions_exec") == len(with_commands - with_pty)
    assert stat(migrated, "commands") == commands
    assert stat(migrated, "sources") == len(sources)


def test_all_combines_both_variants(ingested, migrated, database_url):
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    # In den Fixtures gibt es nur Variante A, "all" muss also gleich sein.
    for metric in ("sessions", "logins", "commands", "sources"):
        assert stat(migrated, metric, variant="all") == stat(migrated, metric)


def test_the_hours_add_up_to_the_sessions(ingested, migrated, database_url):
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    total = scalar(
        migrated,
        select(func.sum(DailyStat.value)).where(
            DailyStat.day == DAY, DailyStat.variant == "a", DailyStat.metric == "sessions_by_hour"
        ),
    )
    assert int(total) == stat(migrated, "sessions")
    hours = scalar(
        migrated,
        select(func.count()).select_from(DailyStat).where(DailyStat.metric == "sessions_by_hour"),
    )
    assert hours > 0


def test_sessions_without_a_country_are_counted_as_unknown(ingested, migrated, database_url):
    """Ohne IPinfo-Datenbank hat keine Sitzung ein Land."""
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    assert stat(migrated, "sessions_by_country", dimension="??") == stat(migrated, "sessions")


def test_running_twice_gives_the_same_rows(ingested, migrated, database_url):
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    first = scalar(migrated, select(func.count()).select_from(DailyStat))
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    second = scalar(migrated, select(func.count()).select_from(DailyStat))
    assert first == second > 0


def test_days_without_statistics_are_filled_even_months_later(ingested, migrated, database_url):
    """Der 17.09. liegt weit vor „heute und gestern“ und fehlt trotzdem nicht."""
    result = run(jobs.aggregate_daily_stats, make_ctx(database_url, MUCH_LATER))
    assert result["von"] == DAY.isoformat()
    assert stat(migrated, "sessions") == len({e["session"] for e in ingested})


def test_all_days_recomputes_everything(ingested, migrated, database_url):
    run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    result = run(jobs.aggregate_daily_stats, make_ctx(database_url, MUCH_LATER), all_days=True)
    assert result["tage"] == 1
    assert result["von"] == result["bis"] == DAY.isoformat()


def test_an_empty_database_is_fine(migrated, database_url):
    result = run(jobs.aggregate_daily_stats, make_ctx(database_url, NEXT_DAY))
    assert result["zeilen"] == 0


# --- Aufräumen --------------------------------------------------------------


def test_recent_events_stay(ingested, migrated, database_url):
    before = scalar(migrated, select(func.count()).select_from(Event))
    result = run(jobs.cleanup_raw_events, make_ctx(database_url, NEXT_DAY))
    assert result["geloescht"] == 0
    assert scalar(migrated, select(func.count()).select_from(Event)) == before


def test_old_events_go_but_sessions_commands_and_statistics_stay(ingested, migrated, database_url):
    sessions = scalar(migrated, select(func.count()).select_from(Session))
    commands = scalar(migrated, select(func.count()).select_from(Command))

    result = run(jobs.cleanup_raw_events, make_ctx(database_url, MUCH_LATER))

    assert result["geloescht"] == len(ingested)
    assert scalar(migrated, select(func.count()).select_from(Event)) == 0
    assert scalar(migrated, select(func.count()).select_from(Session)) == sessions
    assert scalar(migrated, select(func.count()).select_from(Command)) == commands


def test_the_statistics_are_computed_before_the_events_go(ingested, migrated, database_url):
    """Die Logins stammen aus den Events. Danach ließen sie sich nicht mehr zählen."""
    logins = len({e["session"] for e in ingested if e["eventid"] == "cowrie.login.success"})
    run(jobs.cleanup_raw_events, make_ctx(database_url, MUCH_LATER))
    assert stat(migrated, "logins") == logins > 0


def test_deleting_works_in_portions(ingested, migrated, database_url, monkeypatch):
    monkeypatch.setattr(jobs, "DELETE_BATCH", 7)
    result = run(jobs.cleanup_raw_events, make_ctx(database_url, MUCH_LATER))
    assert result["geloescht"] == len(ingested)
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM events")).scalar() == 0
