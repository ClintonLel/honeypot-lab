"""Die Jobs des Workers (Schritt 4.3).

- ``ipinfo``: lädt die IPinfo-Lite-Datenbank, wenn sich ihre Prüfsumme geändert
  hat, und ersetzt die Datei atomar.
- ``statistik``: rechnet ``daily_stats`` für die letzten Tage und für jeden Tag
  ohne Statistik neu.
- ``aufraeumen``: löscht Roh-Events nach 90 Tagen, Sitzungen und Statistik
  bleiben.
- ``attack``: ordnet alle gespeicherten Befehle neu den ATT&CK-Techniken zu
  (Schritt 6.1). Nur von Hand, nach einer Änderung an ``rules/attack.yml``;
  neue Befehle taggt schon der Ingest.
- ``campaigns``: bündelt Sitzungen mit gleicher normalisierter Befehlsfolge
  zu Kampagnen und übernimmt die Labels aus ``rules/campaigns.yml``
  (Schritt 6.2, E-039). Stündlich, voller Neuaufbau.

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
import statistics
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.attack import default_rules
from app.campaigns import (
    LABELS_PATH,
    MIN_SESSIONS,
    PREFIX_LENGTH,
    fingerprint,
    load_labels,
    normalized_sequence,
    opening_hash,
)
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


# --- ATT&CK (Schritt 6.1) ------------------------------------------------------

TAG_BATCH = 2000
UNTAGGED_LIMIT = 100

TAG_SELECT_SQL = text(
    "SELECT id, command, techniques FROM commands WHERE id > :after ORDER BY id LIMIT :batch"
)
TAG_UPDATE_SQL = text("UPDATE commands SET techniques = CAST(:techniques AS jsonb) WHERE id = :id")

UNTAGGED_SQL = text(
    """
    SELECT command, count(*) AS n
    FROM commands
    WHERE techniques = '[]'::jsonb
    GROUP BY command
    ORDER BY n DESC, command
    LIMIT :limit
    """
)
COUNT_SQL = text(
    "SELECT count(*), count(*) FILTER (WHERE techniques = '[]'::jsonb) FROM commands"
)


async def tag_commands(ctx: Context) -> dict[str, Any]:
    """Wendet die aktuellen Regeln auf alle Befehle an. Beliebig oft wiederholbar.

    Geschrieben wird nur, wo sich das Ergebnis ändert. Jede Portion läuft in
    einer eigenen Transaktion, damit der Ingest nicht lange wartet.
    """
    engine = _require_engine(ctx)
    rules = default_rules()
    checked = changed = 0
    after = 0
    while True:
        async with engine.begin() as connection:
            rows = (await connection.execute(TAG_SELECT_SQL, {"after": after, "batch": TAG_BATCH})).all()
            if not rows:
                break
            updates = []
            for command_id, command, current in rows:
                techniques = rules.classify(command)
                if list(current or []) != techniques:
                    updates.append({"id": command_id, "techniques": json.dumps(techniques)})
            if updates:
                await connection.execute(TAG_UPDATE_SQL, updates)
        checked += len(rows)
        changed += len(updates)
        after = rows[-1][0]

    return {"geprueft": checked, "geaendert": changed, "attack_version": rules.attack_version}


async def untagged_report(ctx: Context, limit: int = UNTAGGED_LIMIT) -> dict[str, Any]:
    """Die häufigsten Befehle ohne Technik, für den Report aus Schritt 6.1.

    Die Befehle sind Angreifertext. Sie gehen nie ins Log, sondern nur an
    ``worker.main``, das sie für das Terminal aufbereitet.
    """
    engine = _require_engine(ctx)
    async with engine.connect() as connection:
        total, untagged = (await connection.execute(COUNT_SQL)).one()
        rows = (await connection.execute(UNTAGGED_SQL, {"limit": limit})).all()
    return {
        "befehle": int(total),
        "ohne_technik": int(untagged),
        "haeufigste": [(command, int(count)) for command, count in rows],
    }


# --- Kampagnen (Schritt 6.2) ----------------------------------------------------

CAMPAIGN_BATCH = 2000
CAMPAIGN_REPORT_LIMIT = 20
REPORT_COMMANDS = 3
# Wartet der Job länger auf eine Sperre, bricht er ab, statt den Ingest
# aufzuhalten. Der nächste Lauf versucht es neu.
LOCK_TIMEOUT = "5s"

# Felder, die der Job schreibt. label und description kommen nur aus
# rules/campaigns.yml.
CAMPAIGN_FIELDS = (
    "kind",
    "first_seen",
    "last_seen",
    "sessions_a",
    "sessions_b",
    "countries",
    "techniques",
    "sources",
    "asns",
    "median_interval_s",
    "label",
    "description",
)

SESSION_IDS_SQL = text(
    """
    SELECT DISTINCT session_id FROM commands
    WHERE session_id > :after ORDER BY session_id LIMIT :batch
    """
)
SESSIONS_SQL = text(
    """
    SELECT id, variant, interactive, started_at, country, asn, ip_hash, campaign_id
    FROM sessions WHERE id = ANY(CAST(:ids AS bigint[]))
    """
)
SESSION_COMMANDS_SQL = text(
    """
    SELECT session_id, command, techniques FROM commands
    WHERE session_id = ANY(CAST(:ids AS bigint[]))
    ORDER BY session_id, sequence
    """
)
EXISTING_CAMPAIGNS_SQL = text(
    "SELECT fingerprint, " + ", ".join(CAMPAIGN_FIELDS) + " FROM campaigns"
)
UPSERT_CAMPAIGN_SQL = text(
    """
    INSERT INTO campaigns (fingerprint, kind, first_seen, last_seen, sessions_a, sessions_b,
                           countries, techniques, sources, asns, median_interval_s,
                           label, description)
    VALUES (:fingerprint, :kind, :first_seen, :last_seen, :sessions_a, :sessions_b,
            CAST(:countries AS jsonb), CAST(:techniques AS jsonb), :sources, :asns,
            :median_interval_s, :label, :description)
    ON CONFLICT (fingerprint) DO UPDATE SET
        kind = EXCLUDED.kind,
        first_seen = EXCLUDED.first_seen,
        last_seen = EXCLUDED.last_seen,
        sessions_a = EXCLUDED.sessions_a,
        sessions_b = EXCLUDED.sessions_b,
        countries = EXCLUDED.countries,
        techniques = EXCLUDED.techniques,
        sources = EXCLUDED.sources,
        asns = EXCLUDED.asns,
        median_interval_s = EXCLUDED.median_interval_s,
        label = EXCLUDED.label,
        description = EXCLUDED.description,
        updated_at = now()
    """
)
DELETE_CAMPAIGNS_SQL = text(
    "DELETE FROM campaigns WHERE fingerprint <> ALL(CAST(:fingerprints AS text[]))"
)
CAMPAIGN_IDS_SQL = text("SELECT fingerprint, id FROM campaigns")
ASSIGN_SQL = text("UPDATE sessions SET campaign_id = :campaign_id WHERE id = :id")
# Sitzungen ohne Befehle gehören zu keiner Kampagne. Das greift nur, wenn
# jemand campaign_id von Hand gesetzt hat.
UNASSIGN_WITHOUT_COMMANDS_SQL = text(
    """
    UPDATE sessions SET campaign_id = NULL
    WHERE campaign_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM commands c WHERE c.session_id = sessions.id)
    """
)


@dataclass
class _SessionFacts:
    """Was der Job je Sitzung braucht. ip_hash nur zum Zählen, nie in einer Ausgabe."""

    id: int
    variant: str
    started_at: datetime
    country: str | None
    asn: str | None
    ip_hash: str
    campaign_id: int | None
    techniques: set[str]


def _interval_median(starts: list[datetime]) -> int | None:
    ordered = sorted(starts)
    gaps = [(later - earlier).total_seconds() for earlier, later in zip(ordered, ordered[1:])]
    return round(statistics.median(gaps)) if gaps else None


def campaign_facts(kind: str, sessions: list[_SessionFacts]) -> dict[str, Any]:
    """Die Kennzahlen einer Kampagne aus ihren Sitzungen."""
    countries = Counter(s.country or "??" for s in sessions)
    return {
        "kind": kind,
        "first_seen": min(s.started_at for s in sessions),
        "last_seen": max(s.started_at for s in sessions),
        "sessions_a": sum(1 for s in sessions if s.variant == "a"),
        "sessions_b": sum(1 for s in sessions if s.variant == "b"),
        "countries": dict(sorted(countries.items())),
        "techniques": sorted(set().union(*(s.techniques for s in sessions))),
        "sources": len({s.ip_hash for s in sessions}),
        "asns": len({s.asn for s in sessions if s.asn}),
        "median_interval_s": _interval_median([s.started_at for s in sessions]),
    }


async def _read_fingerprints(
    engine: AsyncEngine,
) -> tuple[dict[str, tuple[str, list[_SessionFacts]]], list[_SessionFacts]]:
    """Liest alle Sitzungen mit Befehlen in Portionen und gruppiert sie."""
    groups: dict[str, tuple[str, list[_SessionFacts]]] = {}
    everyone: list[_SessionFacts] = []
    after = 0
    while True:
        async with engine.connect() as connection:
            ids = list(
                (
                    await connection.execute(
                        SESSION_IDS_SQL, {"after": after, "batch": CAMPAIGN_BATCH}
                    )
                ).scalars()
            )
            if not ids:
                break
            sessions = (await connection.execute(SESSIONS_SQL, {"ids": ids})).all()
            commands = (await connection.execute(SESSION_COMMANDS_SQL, {"ids": ids})).all()
        after = ids[-1]

        texts: dict[int, list[str]] = defaultdict(list)
        techniques: dict[int, set[str]] = defaultdict(set)
        for session_id, command, tags in commands:
            texts[session_id].append(command)
            techniques[session_id].update(tags or [])

        for row in sessions:
            facts = _SessionFacts(
                id=row.id,
                variant=row.variant,
                started_at=row.started_at,
                country=row.country,
                asn=row.asn,
                ip_hash=row.ip_hash,
                campaign_id=row.campaign_id,
                techniques=techniques[row.id],
            )
            everyone.append(facts)
            kind = "interactive" if row.interactive else "exec"
            key = fingerprint(kind, normalized_sequence(texts[row.id]))
            if key is not None:
                groups.setdefault(key, (kind, []))[1].append(facts)
    return groups, everyone


async def build_campaigns(ctx: Context, labels_path: Path = LABELS_PATH) -> dict[str, Any]:
    """Baut alle Kampagnen neu auf. Beliebig oft wiederholbar (E-039).

    Liest alle Sitzungen mit Befehlen, bildet je Sitzung den Fingerprint und
    macht aus jeder Gruppe mit mindestens ``MIN_SESSIONS`` Sitzungen eine
    Kampagne. Geschrieben wird nur, was sich geändert hat, und alles in einer
    Transaktion: Die API sieht entweder den alten oder den neuen Stand.
    """
    engine = _require_engine(ctx)
    # Zuerst, damit eine kaputte Label-Datei nichts halb schreibt.
    labels = load_labels(labels_path)

    groups, everyone = await _read_fingerprints(engine)
    wanted: dict[str, dict[str, Any]] = {}
    members: dict[str, list[_SessionFacts]] = {}
    for key, (kind, sessions) in groups.items():
        if len(sessions) < MIN_SESSIONS:
            continue
        label = labels.get(key[:PREFIX_LENGTH])
        wanted[key] = {
            **campaign_facts(kind, sessions),
            "label": label.label if label else None,
            "description": label.description if label else None,
        }
        members[key] = sessions

    async with engine.begin() as connection:
        await connection.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
        existing = {
            row.fingerprint: {name: getattr(row, name) for name in CAMPAIGN_FIELDS}
            for row in (await connection.execute(EXISTING_CAMPAIGNS_SQL)).all()
        }
        changed = [
            {
                "fingerprint": key,
                **facts,
                "countries": json.dumps(facts["countries"]),
                "techniques": json.dumps(facts["techniques"]),
            }
            for key, facts in sorted(wanted.items())
            if existing.get(key) != facts
        ]
        if changed:
            await connection.execute(UPSERT_CAMPAIGN_SQL, changed)
        removed = await connection.execute(DELETE_CAMPAIGNS_SQL, {"fingerprints": sorted(wanted)})

        ids = {
            key: campaign_id
            for key, campaign_id in (await connection.execute(CAMPAIGN_IDS_SQL)).all()
        }
        target = {s.id: ids[key] for key, sessions in members.items() for s in sessions}
        # Nach id sortiert, damit Sperren immer in derselben Reihenfolge fallen.
        moves = [
            {"id": s.id, "campaign_id": target.get(s.id)}
            for s in sorted(everyone, key=lambda s: s.id)
            if s.campaign_id != target.get(s.id)
        ]
        if moves:
            await connection.execute(ASSIGN_SQL, moves)
        stray = await connection.execute(UNASSIGN_WITHOUT_COMMANDS_SQL)

    new = sum(1 for key in wanted if key not in existing)
    return {
        "sitzungen": len(everyone),
        "fingerprints": len(groups),
        "kampagnen": len(wanted),
        "neu": new,
        "geaendert": len(changed) - new,
        "entfernt": removed.rowcount or 0,
        "zugeordnet": len(target),
        "sitzungen_geaendert": len(moves) + (stray.rowcount or 0),
        "gelabelt": sum(1 for facts in wanted.values() if facts["label"]),
        # Präfixe sind Hashes, kein Angreifertext, und dürfen ins Log.
        "labels_ohne_kampagne": sorted(
            prefix for prefix in labels if not any(key.startswith(prefix) for key in wanted)
        ),
    }


REPORT_CAMPAIGNS_SQL = text(
    """
    SELECT id, fingerprint, label, kind, sessions_a, sessions_b, sources, asns,
           median_interval_s
    FROM campaigns
    ORDER BY sessions_a + sessions_b DESC, id
    LIMIT :limit
    """
)
REPORT_TOTALS_SQL = text("SELECT count(*), count(label) FROM campaigns")
# Die älteste Sitzung jeder Kampagne steht für ihre Befehlsfolge.
REPORT_SAMPLES_SQL = text(
    """
    SELECT DISTINCT ON (campaign_id) campaign_id, id
    FROM sessions
    WHERE campaign_id = ANY(CAST(:ids AS integer[]))
    ORDER BY campaign_id, started_at, id
    """
)
REPORT_COMMANDS_SQL = text(
    """
    SELECT session_id, command FROM commands
    WHERE session_id = ANY(CAST(:ids AS bigint[]))
    ORDER BY session_id, sequence
    """
)


async def campaigns_report(ctx: Context, limit: int = CAMPAIGN_REPORT_LIMIT) -> dict[str, Any]:
    """Die größten Kampagnen mit ihren ersten Befehlen, für den Bericht.

    Die Befehle sind Angreifertext, wenn auch normalisiert. Sie gehen nie ins
    Log, sondern nur an ``worker.main``, das sie für das Terminal aufbereitet.
    """
    engine = _require_engine(ctx)
    async with engine.connect() as connection:
        total, labelled = (await connection.execute(REPORT_TOTALS_SQL)).one()
        rows = (await connection.execute(REPORT_CAMPAIGNS_SQL, {"limit": limit})).all()
        samples = dict(
            (
                await connection.execute(REPORT_SAMPLES_SQL, {"ids": [row.id for row in rows]})
            ).all()
        )
        commands = (
            await connection.execute(REPORT_COMMANDS_SQL, {"ids": list(samples.values())})
        ).all()

    texts: dict[int, list[str]] = defaultdict(list)
    for session_id, command in commands:
        texts[session_id].append(command)

    campaigns = []
    for row in rows:
        sequence = normalized_sequence(texts[samples[row.id]]) if row.id in samples else []
        campaigns.append(
            {
                "prefix": row.fingerprint[:PREFIX_LENGTH],
                "p3": opening_hash(sequence, REPORT_COMMANDS),
                "label": row.label,
                "kind": row.kind,
                "sessions_a": row.sessions_a,
                "sessions_b": row.sessions_b,
                "sources": row.sources,
                "asns": row.asns,
                "median_interval_s": row.median_interval_s,
                "length": len(sequence),
                "commands": sequence[:REPORT_COMMANDS],
            }
        )
    return {"kampagnen": int(total), "gelabelt": int(labelled), "groesste": campaigns}
