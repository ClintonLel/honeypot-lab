"""Die Jobs des Workers (Schritt 4.3).

- ``ipinfo``: lädt die IPinfo-Lite-Datenbank, wenn sich ihre Prüfsumme geändert
  hat, und ersetzt die Datei atomar.
- ``statistik``: rechnet ``daily_stats`` für die letzten Tage und für jeden Tag
  ohne Statistik neu.
- ``aufraeumen``: löscht Roh-Events nach 90 Tagen, Sitzungen und Statistik
  bleiben.

Einen Job zur Rotation des HMAC-Schlüssels gibt es bewusst nicht. Der Bauplan
sah ihn vor, E-022 hat entschieden, dass der Schlüssel fest bleibt.

Jeder Job gibt ein kleines Wörterbuch mit seinem Ergebnis zurück. Das
Protokollieren von Dauer und Ergebnis übernimmt ``worker.main``.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings

# --- IPinfo ------------------------------------------------------------------

LITE_URL = "https://ipinfo.io/data/ipinfo_lite.mmdb"
CHECKSUM_URL = "https://ipinfo.io/data/ipinfo_lite.mmdb/checksums"

# Die Lite-Datenbank ist einige Dutzend MB groß. Alles deutlich darüber ist
# kein IPinfo-Download mehr, sondern ein Fehler.
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT = 120
CHECKSUM_TIMEOUT = 30
CHUNK = 1024 * 1024

# Eine bekannte, öffentliche Adresse für die Probeabfrage. Sie wird nie
# geloggt und gehört keinem Angreifer.
PROBE_ADDRESS = "1.1.1.1"


class DownloadError(RuntimeError):
    """Fehler beim Download. Die Meldung enthält nie URL oder Token."""


Opener = Callable[[str, float], BinaryIO]
Validator = Callable[[Path], None]


def default_opener(url: str, timeout: float) -> BinaryIO:
    request = urllib.request.Request(url, headers={"User-Agent": "honeypot-lab-worker"})
    try:
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - feste https-URL
    except urllib.error.HTTPError as exc:
        # Nur der Status. Die URL enthält das Token.
        raise DownloadError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DownloadError(f"Verbindung fehlgeschlagen ({type(exc).__name__})") from None


def validate_mmdb(path: Path) -> None:
    """Öffnet die Datei probeweise und fragt eine bekannte Adresse ab."""
    import maxminddb

    try:
        with maxminddb.open_database(str(path)) as reader:
            if reader.metadata().node_count <= 0:
                raise DownloadError("Datenbank ist leer")
            record = reader.get(PROBE_ADDRESS)
    except DownloadError:
        raise
    except Exception as exc:  # noqa: BLE001 - jede kaputte Datei landet hier
        raise DownloadError(f"Datei lässt sich nicht lesen ({type(exc).__name__})") from None
    if not isinstance(record, dict) or not record.get("country_code"):
        raise DownloadError("Probeabfrage liefert kein Land")


def with_token(url: str, token: str) -> str:
    return f"{url}?{urlencode({'token': token})}"


def sha256_of(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def find_sha256(data: Any) -> str | None:
    """Sucht die SHA-256-Prüfsumme in der Antwort, wo auch immer sie steht."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() == "sha256" and isinstance(value, str):
                return value.strip().lower()
        for value in data.values():
            found = find_sha256(value)
            if found:
                return found
    return None


@dataclass
class Context:
    """Was ein Job braucht. Tests ersetzen Uhr, Downloader und Prüfung."""

    settings: Settings
    engine: AsyncEngine | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    opener: Opener = default_opener
    validator: Validator = validate_mmdb


def _fetch_checksum(ctx: Context, token: str) -> str | None:
    with ctx.opener(with_token(CHECKSUM_URL, token), CHECKSUM_TIMEOUT) as response:
        raw = response.read(65536)
    try:
        return find_sha256(json.loads(raw))
    except (ValueError, UnicodeDecodeError):
        return None


def _download(ctx: Context, token: str, part: Path) -> tuple[int, str]:
    digest = sha256()
    size = 0
    try:
        with ctx.opener(with_token(LITE_URL, token), DOWNLOAD_TIMEOUT) as response, part.open("wb") as out:
            while chunk := response.read(CHUNK):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise DownloadError("Datei größer als erwartet")
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        raise DownloadError(f"Download abgebrochen ({type(exc).__name__})") from None
    return size, digest.hexdigest()


def _update_ipinfo(ctx: Context) -> dict[str, Any]:
    token = ctx.settings.ipinfo_token.get_secret_value()
    if not token:
        return {"status": "übersprungen", "grund": "IPINFO_TOKEN fehlt"}

    target = Path(ctx.settings.ipinfo_db_path)
    if not os.access(target.parent, os.W_OK):
        raise DownloadError(f"{target.parent} ist nicht beschreibbar")

    # Die Prüfsumme zählt bei IPinfo nicht gegen das Limit von 10 Downloads
    # am Tag. Ist sie unverändert, bleibt es beim Nachfragen.
    remote = _fetch_checksum(ctx, token)
    if remote and target.exists() and sha256_of(target) == remote:
        return {"status": "unverändert", "sha256": remote[:16]}

    # Die Zwischendatei liegt im selben Verzeichnis, sonst wäre os.replace
    # nicht atomar. Die API sieht immer entweder die alte oder die neue Datei.
    # Die Prozessnummer im Namen trennt einen Einzellauf von der Schleife.
    part = target.with_name(f".{target.name}.{os.getpid()}.part")
    try:
        size, local = _download(ctx, token, part)
        if remote and local != remote:
            raise DownloadError("Prüfsumme stimmt nicht")
        ctx.validator(part)
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)

    return {
        "status": "aktualisiert",
        "bytes": size,
        "sha256": local[:16],
        "pruefsumme": "geprüft" if remote else "nicht verfügbar",
    }


async def update_ipinfo(ctx: Context) -> dict[str, Any]:
    """Lädt die IPinfo-Lite-Datenbank, wenn es eine neue gibt."""
    return await asyncio.to_thread(_update_ipinfo, ctx)


def ipinfo_age(ctx: Context) -> timedelta | None:
    target = Path(ctx.settings.ipinfo_db_path)
    try:
        mtime = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return ctx.now() - mtime


# --- Tagesstatistik ----------------------------------------------------------

# Eine Anweisung für alle Kennzahlen. GROUPING SETS liefert je Tag die Zeilen
# je Variante und eine Zeile für beide zusammen (variant NULL, wird zu "all").
# Grundlage sind sessions und commands, nicht die Roh-Events: Die verschwinden
# nach 90 Tagen, die Statistik muss sich trotzdem nachrechnen lassen. Nur die
# Logins kommen aus events, solange es sie gibt.
AGGREGATE_SQL = text(
    """
    WITH s AS (
        SELECT
            se.variant,
            se.ip_hash,
            COALESCE(se.country, '??') AS country,
            se.interactive,
            se.command_count,
            (se.started_at AT TIME ZONE 'UTC')::date AS day,
            to_char(se.started_at AT TIME ZONE 'UTC', 'HH24') AS hour,
            EXISTS (
                SELECT 1 FROM events e
                WHERE e.session_id = se.id AND e.eventid = 'cowrie.login.success'
            ) AS logged_in
        FROM sessions se
        WHERE (se.started_at AT TIME ZONE 'UTC')::date = ANY(:days)
    ),
    totals AS (
        SELECT
            day,
            variant,
            count(*) AS sessions,
            count(*) FILTER (WHERE logged_in) AS logins,
            count(*) FILTER (WHERE interactive IS TRUE) AS sessions_interactive,
            count(*) FILTER (WHERE interactive IS FALSE) AS sessions_exec,
            COALESCE(sum(command_count), 0) AS commands,
            count(DISTINCT ip_hash) AS sources
        FROM s
        GROUP BY GROUPING SETS ((day, variant), (day))
    ),
    by_country AS (
        SELECT day, variant, country AS dimension, count(*) AS value
        FROM s
        GROUP BY GROUPING SETS ((day, variant, country), (day, country))
    ),
    by_hour AS (
        SELECT day, variant, hour AS dimension, count(*) AS value
        FROM s
        GROUP BY GROUPING SETS ((day, variant, hour), (day, hour))
    )
    INSERT INTO daily_stats (day, variant, metric, dimension, value, updated_at)
    SELECT t.day, COALESCE(t.variant, 'all'), m.metric, '', m.value, now()
    FROM totals t
    CROSS JOIN LATERAL (
        VALUES
            ('sessions', t.sessions),
            ('logins', t.logins),
            ('sessions_interactive', t.sessions_interactive),
            ('sessions_exec', t.sessions_exec),
            ('commands', t.commands),
            ('sources', t.sources)
    ) AS m(metric, value)
    UNION ALL
    SELECT day, COALESCE(variant, 'all'), 'sessions_by_country', dimension, value, now()
    FROM by_country
    UNION ALL
    SELECT day, COALESCE(variant, 'all'), 'sessions_by_hour', dimension, value, now()
    FROM by_hour
    """
)

DELETE_STATS_SQL = text("DELETE FROM daily_stats WHERE day = ANY(:days)")

ALL_DAYS_SQL = text(
    "SELECT DISTINCT (started_at AT TIME ZONE 'UTC')::date FROM sessions ORDER BY 1"
)
GAP_DAYS_SQL = text(
    """
    SELECT DISTINCT s.day FROM (
        SELECT (started_at AT TIME ZONE 'UTC')::date AS day FROM sessions
    ) AS s
    WHERE NOT EXISTS (SELECT 1 FROM daily_stats ds WHERE ds.day = s.day)
    ORDER BY 1
    """
)

# Wie weit zurück die Statistik bei jedem Lauf neu entsteht. Sitzungen enden
# oft erst nach dem Tageswechsel, deshalb auch gestern.
RECENT_DAYS = 2


def _require_engine(ctx: Context) -> AsyncEngine:
    if ctx.engine is None:
        raise RuntimeError("keine Datenbank im Kontext")
    return ctx.engine


async def aggregate_daily_stats(ctx: Context, all_days: bool = False) -> dict[str, Any]:
    """Rechnet daily_stats für die fälligen Tage neu. Beliebig oft wiederholbar."""
    engine = _require_engine(ctx)
    today = ctx.now().date()
    async with engine.begin() as connection:
        if all_days:
            days = list((await connection.execute(ALL_DAYS_SQL)).scalars())
        else:
            recent = {today - timedelta(days=offset) for offset in range(RECENT_DAYS)}
            gaps = set((await connection.execute(GAP_DAYS_SQL)).scalars())
            days = sorted(recent | gaps)

        if not days:
            return {"tage": 0, "zeilen": 0}

        # Löschen und neu schreiben in einer Transaktion: Wer liest, sieht
        # entweder die alte oder die neue Statistik, nie eine halbe.
        await connection.execute(DELETE_STATS_SQL, {"days": days})
        result = await connection.execute(AGGREGATE_SQL, {"days": days})

    return {
        "tage": len(days),
        "von": min(days).isoformat(),
        "bis": max(days).isoformat(),
        "zeilen": result.rowcount,
    }


# --- Aufräumen ---------------------------------------------------------------

DELETE_BATCH = 5000

DELETE_OLD_EVENTS_SQL = text(
    """
    DELETE FROM events
    WHERE id IN (
        SELECT id FROM events WHERE occurred_at < :cutoff ORDER BY id LIMIT :batch
    )
    """
)


async def cleanup_raw_events(ctx: Context) -> dict[str, Any]:
    """Löscht Roh-Events, die älter sind als die Aufbewahrungsfrist."""
    engine = _require_engine(ctx)
    cutoff = ctx.now() - timedelta(days=ctx.settings.raw_event_retention_days)

    # Erst sicherstellen, dass jeder Tag seine Statistik hat. Die Logins
    # stammen aus den Events, danach ließen sie sich nicht mehr zählen.
    backfill = await aggregate_daily_stats(ctx)

    deleted = 0
    while True:
        # Jede Portion in einer eigenen Transaktion, damit der Ingest nicht
        # lange auf gesperrte Zeilen wartet.
        async with engine.begin() as connection:
            result = await connection.execute(
                DELETE_OLD_EVENTS_SQL, {"cutoff": cutoff, "batch": DELETE_BATCH}
            )
        deleted += result.rowcount or 0
        if (result.rowcount or 0) < DELETE_BATCH:
            break

    return {
        "geloescht": deleted,
        "stichtag": cutoff.date().isoformat(),
        "statistik_tage_vorher": backfill["tage"],
    }
