"""GET /stats/*: Kennzahlen für die Seite /lab (Schritt 5.1, /recent aus 5.2).

Grundlage ist ``daily_stats``, die der Worker stündlich rechnet (E-028). Nur
„heute“ in der Übersicht kommt live aus ``sessions``, sonst hinkte der Kopf der
Seite bis zu einer Stunde hinterher.

Jede Antwort bleibt 30 Sekunden im Speicher und darf 30 Sekunden gecacht
werden. Die Uhr ist über ``app.state.clock`` austauschbar, damit Tests „heute“
auf den Tag ihrer Beispieldaten legen können.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.defang import shorten
from app.models import Campaign
from app.ratelimit import rate_limited
from app.stream import PREVIEW_LENGTH

router = APIRouter(prefix="/stats", dependencies=[Depends(rate_limited)])

CACHE_SECONDS = 30
VARIANTS = ("a", "b", "all")
# Liefert der Sensor so lange nichts, gilt er auf der Seite als offline.
ONLINE_WINDOW = timedelta(minutes=15)
TOP_COUNTRIES = 50
TOP_CAMPAIGNS = 10
RECENT_COMMANDS = 12
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

Days = Query(default=30, ge=1, le=365, description="Zeitraum in Tagen bis einschließlich heute")


class TTLCache:
    """Kleiner Cache im Speicher. Parallele Anfragen rechnen nur einmal."""

    def __init__(self, ttl: float = CACHE_SECONDS, max_entries: int = 512) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._locks: dict[Any, asyncio.Lock] = {}

    async def get(self, key: Any, compute: Callable[[], Awaitable[Any]]) -> Any:
        entry = self._entries.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._entries.get(key)
            if entry and entry[0] > time.monotonic():
                return entry[1]
            value = await compute()
            self._entries[key] = (time.monotonic() + self.ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                old, _ = self._entries.popitem(last=False)
                self._locks.pop(old, None)
            return value


def today_of(request: Request) -> date:
    return request.app.state.clock().astimezone(timezone.utc).date()


def cached(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"


async def _rows(engine: AsyncEngine, statement, params: dict[str, Any] | None = None) -> list[Any]:
    async with engine.connect() as connection:
        return list((await connection.execute(statement, params or {})).all())


def _window(today: date, days: int) -> dict[str, date]:
    return {"first": today - timedelta(days=days - 1), "last": today}


def empty_counts(keys: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {variant: {key: 0 for key in keys} for variant in VARIANTS}


# --- Übersicht ---------------------------------------------------------------

TODAY_SQL = text(
    """
    SELECT
        se.variant,
        count(*) AS sessions,
        count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM events e
            WHERE e.session_id = se.id AND e.eventid = 'cowrie.login.success'
        )) AS logins,
        COALESCE(sum(se.command_count), 0) AS commands
    FROM sessions se
    WHERE se.started_at >= :start AND se.started_at < :end
    GROUP BY se.variant
    """
)

BEFORE_TODAY_SQL = text(
    """
    SELECT variant, metric, sum(value) AS value
    FROM daily_stats
    WHERE day < :today AND dimension = '' AND metric IN ('sessions', 'logins', 'commands')
    GROUP BY variant, metric
    """
)

SINCE_SQL = text("SELECT min(started_at) FROM sessions")
LAST_EVENT_SQL = text("SELECT max(created_at) FROM events")

OVERVIEW_KEYS = ("sessions", "logins", "commands")


async def overview_data(engine: AsyncEngine, now: datetime) -> dict[str, Any]:
    today = now.date()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    live = empty_counts(OVERVIEW_KEYS)
    for variant, sessions, logins, commands in await _rows(
        engine, TODAY_SQL, {"start": start, "end": start + timedelta(days=1)}
    ):
        for target in (variant, "all"):
            live[target]["sessions"] += int(sessions)
            live[target]["logins"] += int(logins)
            live[target]["commands"] += int(commands)

    total = empty_counts(OVERVIEW_KEYS)
    for variant, metric, value in await _rows(engine, BEFORE_TODAY_SQL, {"today": today}):
        if variant in total:
            total[variant][metric] = int(value)
    for variant in VARIANTS:
        for key in OVERVIEW_KEYS:
            total[variant][key] += live[variant][key]

    since = (await _rows(engine, SINCE_SQL))[0][0]
    last_event = (await _rows(engine, LAST_EVENT_SQL))[0][0]
    online = last_event is not None and now - last_event <= ONLINE_WINDOW

    return {
        "generated_at": _iso(now),
        "sensor": {"online": online, "last_event_at": _iso(last_event)},
        "today": live,
        "total": {"since": since.date().isoformat() if since else None, **total},
    }


@router.get("/overview")
async def overview(request: Request, response: Response) -> dict[str, Any]:
    cached(response)
    now = request.app.state.clock().astimezone(timezone.utc)
    # Die Minute im Schlüssel sorgt dafür, dass „heute“ nach Mitternacht nicht
    # 30 Sekunden lang der alte Tag bleibt.
    key = ("overview", now.replace(second=0, microsecond=0))
    return await request.app.state.stats_cache.get(key, lambda: overview_data(request.app.state.engine, now))


# --- Länder ------------------------------------------------------------------

COUNTRIES_SQL = text(
    """
    SELECT dimension AS country, variant, sum(value) AS value
    FROM daily_stats
    WHERE metric = 'sessions_by_country' AND day BETWEEN :first AND :last
    GROUP BY dimension, variant
    """
)


def pivot_countries(rows: list[Any], limit: int = TOP_COUNTRIES) -> list[dict[str, Any]]:
    table: dict[str, dict[str, int]] = {}
    for country, variant, value in rows:
        entry = table.setdefault(country, {"a": 0, "b": 0, "all": 0})
        if variant in entry:
            entry[variant] = int(value)
    ordered = sorted(table.items(), key=lambda item: (-item[1]["all"], item[0]))
    return [{"country": country, **counts} for country, counts in ordered[:limit]]


@router.get("/countries")
async def countries(request: Request, response: Response, days: int = Days) -> dict[str, Any]:
    cached(response)
    today = today_of(request)

    async def compute() -> dict[str, Any]:
        rows = await _rows(request.app.state.engine, COUNTRIES_SQL, _window(today, days))
        return {"days": days, "until": today.isoformat(), "countries": pivot_countries(rows)}

    return await request.app.state.stats_cache.get(("countries", today, days), compute)


# --- Heatmap -----------------------------------------------------------------

HEATMAP_SQL = text(
    """
    SELECT extract(isodow FROM day)::int AS weekday, dimension AS hour, sum(value) AS value
    FROM daily_stats
    WHERE metric = 'sessions_by_hour' AND variant = :variant AND day BETWEEN :first AND :last
    GROUP BY 1, 2
    """
)


def heatmap_matrix(rows: list[Any]) -> list[list[int]]:
    """7 Zeilen (Montag bis Sonntag) mal 24 Spalten (Stunde in UTC)."""
    matrix = [[0] * 24 for _ in range(7)]
    for weekday, hour, value in rows:
        matrix[int(weekday) - 1][int(hour)] = int(value)
    return matrix


@router.get("/heatmap")
async def heatmap(
    request: Request,
    response: Response,
    days: int = Query(default=28, ge=1, le=365),
    variant: str = Query(default="all", pattern="^(a|b|all)$"),
) -> dict[str, Any]:
    cached(response)
    today = today_of(request)

    async def compute() -> dict[str, Any]:
        rows = await _rows(
            request.app.state.engine, HEATMAP_SQL, {"variant": variant, **_window(today, days)}
        )
        matrix = heatmap_matrix(rows)
        return {
            "days": days,
            "until": today.isoformat(),
            "variant": variant,
            "timezone": "UTC",
            "weekdays": list(WEEKDAYS),
            "values": matrix,
            "max": max(max(row) for row in matrix),
        }

    return await request.app.state.stats_cache.get(("heatmap", today, days, variant), compute)


# --- Exec gegen interaktiv ----------------------------------------------------

BREAKDOWN_SQL = text(
    """
    SELECT variant, metric, sum(value) AS value
    FROM daily_stats
    WHERE dimension = '' AND day BETWEEN :first AND :last
      AND metric IN ('sessions', 'sessions_interactive', 'sessions_exec')
    GROUP BY variant, metric
    """
)


def breakdown_table(rows: list[Any]) -> dict[str, dict[str, int]]:
    raw = empty_counts(("sessions", "sessions_interactive", "sessions_exec"))
    for variant, metric, value in rows:
        if variant in raw:
            raw[variant][metric] = int(value)
    return {
        variant: {
            "sessions": counts["sessions"],
            "interactive": counts["sessions_interactive"],
            "exec": counts["sessions_exec"],
            # Ohne Befehl: nur verbunden, nur Login versucht oder eingeloggt
            # und gleich wieder weg.
            "without_commands": counts["sessions"] - counts["sessions_interactive"] - counts["sessions_exec"],
        }
        for variant, counts in raw.items()
    }


@router.get("/breakdown")
async def breakdown(request: Request, response: Response, days: int = Days) -> dict[str, Any]:
    cached(response)
    today = today_of(request)

    async def compute() -> dict[str, Any]:
        rows = await _rows(request.app.state.engine, BREAKDOWN_SQL, _window(today, days))
        return {"days": days, "until": today.isoformat(), "variants": breakdown_table(rows)}

    return await request.app.state.stats_cache.get(("breakdown", today, days), compute)


# --- Letzte Befehle ----------------------------------------------------------

RECENT_SQL = text(
    """
    SELECT c.occurred_at, se.variant, se.country, c.command, c.techniques
    FROM commands c
    JOIN sessions se ON se.id = c.session_id
    ORDER BY c.occurred_at DESC, c.id DESC
    LIMIT :limit
    """
)


def recent_messages(rows: list[Any]) -> list[dict[str, Any]]:
    """Dieselbe Form wie eine Befehlsmeldung im Stream, älteste zuerst.

    ``commands.command`` ist beim Ingest schon ohne Adresse des Angreifers
    und entschärft gespeichert worden (E-024). Hier nur noch auf die Länge
    der Vorschau.
    """
    return [
        {
            "ts": _iso(occurred_at),
            "variant": variant,
            "country": country,
            "event": "command",
            "command": shorten(command, PREVIEW_LENGTH),
            "techniques": list(techniques or []),
        }
        for occurred_at, variant, country, command, techniques in reversed(rows)
    ]


@router.get("/recent")
async def recent(request: Request, response: Response) -> dict[str, Any]:
    """Die letzten Befehle, damit die Seite nicht mit leerer Liste startet."""
    cached(response)

    async def compute() -> dict[str, Any]:
        rows = await _rows(request.app.state.engine, RECENT_SQL, {"limit": RECENT_COMMANDS})
        return {"messages": recent_messages(rows)}

    return await request.app.state.stats_cache.get(("recent",), compute)


# --- Kampagnen ---------------------------------------------------------------


@router.get("/campaigns")
async def campaigns(request: Request, response: Response) -> dict[str, Any]:
    """Die größten Kampagnen. Leer, bis Schritt 6.2 die Tabelle füllt."""
    cached(response)

    async def compute() -> dict[str, Any]:
        statement = (
            select(
                Campaign.label,
                Campaign.description,
                Campaign.kind,
                Campaign.first_seen,
                Campaign.last_seen,
                Campaign.sessions_a,
                Campaign.sessions_b,
                Campaign.countries,
                Campaign.techniques,
            )
            .order_by((Campaign.sessions_a + Campaign.sessions_b).desc(), Campaign.id)
            .limit(TOP_CAMPAIGNS)
        )
        async with request.app.state.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return {
            "campaigns": [
                {
                    "label": row["label"],
                    "description": row["description"],
                    "kind": row["kind"],
                    "first_seen": _iso(row["first_seen"]),
                    "last_seen": _iso(row["last_seen"]),
                    "sessions": {"a": row["sessions_a"], "b": row["sessions_b"]},
                    "countries": row["countries"],
                    "techniques": row["techniques"],
                }
                for row in rows
            ]
        }

    return await request.app.state.stats_cache.get(("campaigns",), compute)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
