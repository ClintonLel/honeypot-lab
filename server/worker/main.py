"""Der Worker: eine Zeitplanschleife für die Jobs aus ``worker.jobs``.

Aufruf im Container:

    python -m worker.main                        # Dauerbetrieb nach Zeitplan
    python -m worker.main run ipinfo             # ein Job, einmal, dann Ende
    python -m worker.main run statistik --alle-tage
    python -m worker.main run alle
    python -m worker.main run attack             # Befehle neu taggen (nur von Hand)
    python -m worker.main run attack --bericht   # dazu die häufigsten ohne Tag
    python -m worker.main run campaigns          # Kampagnen neu aufbauen
    python -m worker.main run campaigns --bericht  # dazu die 20 größten

Jeder Lauf loggt Dauer und Ergebnis. Ein fehlgeschlagener Job beendet den
Worker nicht, er kommt beim nächsten Takt wieder dran.

Der Worker hängt in ``lab_internal`` und ``lab_egress``: Er erreicht die
Datenbank und das Internet, aber niemand erreicht ihn. Einen Job zur Rotation
des HMAC-Schlüssels gibt es nicht, der Schlüssel bleibt fest (E-022).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db import create_engine
from app.logging import configure_logging
from worker import jobs

logger = logging.getLogger("lab.worker")

# Wie oft die Schleife nachsieht, ob ein Job fällig ist.
TICK_SECONDS = 60


@dataclass(frozen=True)
class Job:
    name: str
    interval: timedelta
    run: Callable[[jobs.Context], Awaitable[dict[str, Any]]]
    # Wann der Job nach dem Start zum ersten Mal läuft.
    first_run: Callable[[jobs.Context], datetime]


def _right_away(ctx: jobs.Context) -> datetime:
    return ctx.now()


def _ipinfo_first_run(ctx: jobs.Context) -> datetime:
    """Sofort, wenn die Datei fehlt oder älter als ein Tag ist.

    IPinfo erlaubt 10 Downloads am Tag. Ein Worker, der nach jedem Neustart
    sofort lädt, liefe bei einer Neustartschleife in dieses Limit.
    """
    age = jobs.ipinfo_age(ctx)
    if age is None or age >= IPINFO.interval:
        return ctx.now()
    return ctx.now() + (IPINFO.interval - age)


IPINFO = Job("ipinfo", timedelta(days=1), jobs.update_ipinfo, _ipinfo_first_run)
STATISTIK = Job("statistik", timedelta(hours=1), jobs.aggregate_daily_stats, _right_away)
AUFRAEUMEN = Job("aufraeumen", timedelta(days=1), jobs.cleanup_raw_events, _right_away)
# Voller Neuaufbau der Kampagnen, stündlich wie die Statistik (E-039).
CAMPAIGNS = Job("campaigns", timedelta(hours=1), jobs.build_campaigns, _right_away)

JOBS = (IPINFO, STATISTIK, AUFRAEUMEN, CAMPAIGNS)

# Läuft nur auf Zuruf, nicht im Zeitplan und nicht bei "alle": Neue Befehle
# taggt schon der Ingest, nachgetaggt wird nur nach einer Regeländerung (E-037).
ATTACK = Job("attack", timedelta(0), jobs.tag_commands, _right_away)
MANUAL_JOBS = (ATTACK,)

BY_NAME = {job.name: job for job in (*JOBS, *MANUAL_JOBS)}

# Breite einer Zeile im Report. Längere Befehle werden gekürzt.
REPORT_WIDTH = 200


def safe_detail(exc: BaseException) -> str:
    """Nur Meldungen, die wir selbst geschrieben haben, landen im Log.

    Fremde Ausnahmen können Verbindungsdaten oder SQL mit Parametern enthalten,
    deshalb von ihnen nur der Typ.
    """
    if isinstance(exc, jobs.DownloadError):
        return str(exc)
    return type(exc).__name__


async def run_job(job: Job, ctx: jobs.Context, **kwargs: Any) -> bool:
    """Führt einen Job aus und loggt Dauer und Ergebnis. Wirft nie."""
    started = time.perf_counter()
    try:
        result = await job.run(ctx, **kwargs)
    except Exception as exc:  # noqa: BLE001 - ein Job darf den Worker nicht beenden
        logger.error(
            "job fehlgeschlagen",
            extra={
                "job": job.name,
                "dauer_ms": round((time.perf_counter() - started) * 1000),
                "fehler": safe_detail(exc),
            },
        )
        return False
    logger.info(
        "job fertig",
        extra={
            "job": job.name,
            "dauer_ms": round((time.perf_counter() - started) * 1000),
            "ergebnis": result,
        },
    )
    return True


def printable(command: str, width: int = REPORT_WIDTH) -> str:
    """Macht Angreifertext fürs Terminal harmlos.

    Steuerzeichen, etwa Escape-Sequenzen, erscheinen als ``\\x1b`` und
    steuern das Terminal nicht. Der Text ist beim Ingest schon entschärft.
    """
    visible = "".join(
        ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii") for ch in command
    )
    return visible if len(visible) <= width else visible[: width - 1] + "…"


def format_interval(seconds: int | None) -> str:
    """Abstand grob und kurz: 42s, 7m, 3h, 2d."""
    if seconds is None:
        return "–"
    for unit, size, limit in (("s", 1, 120), ("m", 60, 7200), ("h", 3600, 172800)):
        if seconds < limit:
            return f"{round(seconds / size)}{unit}"
    return f"{round(seconds / 86400)}d"


def format_campaign_report(report: dict[str, Any]) -> str:
    """Tabelle der größten Kampagnen, darunter je die ersten Befehle.

    ``p3`` ist ein Hash über die ersten drei Befehle: Teilen sich mehrere
    Zeilen denselben Wert, beginnen die Kampagnen gleich und laufen erst
    später auseinander.
    """
    campaigns = report["groesste"]
    lines = [
        f"Kampagnen: {report['kampagnen']}, davon mit Label: {report['gelabelt']}",
        f"Die {len(campaigns)} größten:",
        f"{'praefix':<12}  {'p3':<6}  {'art':<11}  {'a':>6}  {'b':>6}  {'quellen':>7}"
        f"  {'asns':>5}  {'abstand':>7}  {'befehle':>7}  label",
    ]
    for c in campaigns:
        lines.append(
            f"{c['prefix']:<12}  {c['p3']:<6}  {c['kind']:<11}  {c['sessions_a']:>6}"
            f"  {c['sessions_b']:>6}  {c['sources']:>7}  {c['asns']:>5}"
            f"  {format_interval(c['median_interval_s']):>7}  {c['length']:>7}"
            f"  {printable(c['label'] or '–', REPORT_WIDTH)}"
        )
        lines += [
            printable(f"    {number}. {command}")
            for number, command in enumerate(c["commands"], start=1)
        ]
    return "\n".join(lines)


def format_report(report: dict[str, Any]) -> str:
    total, untagged = report["befehle"], report["ohne_technik"]
    share = f"{untagged / total:.0%}" if total else "–"
    lines = [
        f"Befehle gesamt: {total}, ohne ATT&CK-Technik: {untagged} ({share})",
        f"Die {len(report['haeufigste'])} häufigsten Befehle ohne Technik:",
    ]
    lines += [f"{count:>8}  {printable(command)}" for command, count in report["haeufigste"]]
    return "\n".join(lines)


# Berichte für --bericht: Job -> (Daten holen, fürs Terminal formatieren).
REPORTS = {
    ATTACK.name: (jobs.untagged_report, format_report),
    CAMPAIGNS.name: (jobs.campaigns_report, format_campaign_report),
}


async def run_forever(ctx: jobs.Context, stopping: asyncio.Event) -> None:
    next_run = {job.name: job.first_run(ctx) for job in JOBS}
    logger.info(
        "worker gestartet",
        extra={"naechste_laeufe": {name: when.isoformat(timespec="seconds") for name, when in next_run.items()}},
    )
    while not stopping.is_set():
        for job in JOBS:
            if stopping.is_set():
                break
            if ctx.now() >= next_run[job.name]:
                await run_job(job, ctx)
                next_run[job.name] = ctx.now() + job.interval
        with suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=TICK_SECONDS)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m worker.main")
    commands = parser.add_subparsers(dest="command")
    once = commands.add_parser("run", help="einen Job einmal ausführen")
    once.add_argument("job", choices=[*BY_NAME, "alle"])
    once.add_argument(
        "--alle-tage",
        action="store_true",
        help="statistik: jeden Tag neu rechnen, etwa nach nachgelieferten Ländern",
    )
    once.add_argument(
        "--bericht",
        action="store_true",
        help="attack: danach die häufigsten Befehle ohne Technik ausgeben; "
        "campaigns: danach die größten Kampagnen",
    )
    args = parser.parse_args(argv)
    if args.command == "run" and args.bericht and args.job not in REPORTS:
        parser.error("--bericht gibt es nur für attack und campaigns")

    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    ctx = jobs.Context(settings=settings, engine=engine)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        if args.command == "run":
            selected = JOBS if args.job == "alle" else (BY_NAME[args.job],)
            results = []
            for job in selected:
                kwargs = {"all_days": True} if job is STATISTIK and args.alle_tage else {}
                results.append(await run_job(job, ctx, **kwargs))
            if args.bericht and all(results):
                # Auf stdout, nicht ins Log: Die Befehle sind Angreifertext.
                collect, render = REPORTS[args.job]
                print(render(await collect(ctx)))
            return 0 if all(results) else 1

        stopping = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, stopping.set)
        await run_forever(ctx, stopping)
        return 0
    finally:
        await engine.dispose()
        logger.info("worker beendet")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
