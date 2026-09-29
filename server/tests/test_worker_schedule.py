"""Prüft den Zeitplan des Workers und das Protokoll der Läufe."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from worker import jobs, main
from worker.main import IPINFO, JOBS, Job, run_job, safe_detail

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def ctx_with_file(tmp_path: Path, age: timedelta | None) -> jobs.Context:
    target = tmp_path / "ipinfo.mmdb"
    if age is not None:
        target.write_bytes(b"x")
        stamp = (NOW - age).timestamp()
        os.utime(target, (stamp, stamp))
    settings = Settings(environment="test", ipinfo_db_path=str(target))
    return jobs.Context(settings=settings, now=lambda: NOW)


def test_the_jobs_from_the_plan_are_there():
    assert {job.name for job in JOBS} == {"ipinfo", "statistik", "aufraeumen"}


def test_there_is_no_key_rotation():
    """Der Bauplan sah sie vor, E-022 hat anders entschieden."""
    names = " ".join(job.name for job in JOBS) + " ".join(dir(jobs))
    assert "rotat" not in names.lower()
    assert "hmac" not in names.lower()


def test_the_intervals_match_the_plan():
    by_name = {job.name: job.interval for job in JOBS}
    assert by_name == {
        "ipinfo": timedelta(days=1),
        "statistik": timedelta(hours=1),
        "aufraeumen": timedelta(days=1),
    }


def test_ipinfo_runs_at_once_without_a_file(tmp_path):
    assert IPINFO.first_run(ctx_with_file(tmp_path, None)) == NOW


def test_ipinfo_runs_at_once_when_the_file_is_old(tmp_path):
    assert IPINFO.first_run(ctx_with_file(tmp_path, timedelta(days=2))) == NOW


def test_ipinfo_waits_when_the_file_is_fresh(tmp_path):
    """Sonst lädt jede Neustartschleife neu, und IPinfo erlaubt 10 am Tag."""
    first = IPINFO.first_run(ctx_with_file(tmp_path, timedelta(hours=1)))
    assert abs(first - (NOW + timedelta(hours=23))) < timedelta(seconds=2)


def test_a_successful_run_logs_duration_and_result(caplog):
    async def fine(ctx):
        return {"zeilen": 3}

    job = Job("probe", timedelta(hours=1), fine, lambda ctx: NOW)
    with caplog.at_level(logging.INFO, logger="lab.worker"):
        assert asyncio.run(run_job(job, None)) is True
    record = next(r for r in caplog.records if r.getMessage() == "job fertig")
    assert record.job == "probe"
    assert record.ergebnis == {"zeilen": 3}
    assert isinstance(record.dauer_ms, int)


def test_a_failing_job_does_not_stop_the_worker(caplog):
    async def broken(ctx):
        raise ValueError("postgresql+psycopg://honeypot:geheim@db/honeypot")

    job = Job("probe", timedelta(hours=1), broken, lambda ctx: NOW)
    with caplog.at_level(logging.INFO, logger="lab.worker"):
        assert asyncio.run(run_job(job, None)) is False
    record = next(r for r in caplog.records if r.getMessage() == "job fehlgeschlagen")
    # Von fremden Ausnahmen nur der Typ: Die Meldung könnte Zugangsdaten tragen.
    assert record.fehler == "ValueError"
    assert "geheim" not in str(record.__dict__)


def test_own_download_errors_keep_their_message():
    assert safe_detail(jobs.DownloadError("HTTP 401")) == "HTTP 401"
    assert safe_detail(RuntimeError("irgendwas")) == "RuntimeError"


def test_the_loop_runs_each_due_job_once_and_stops(monkeypatch):
    runs: list[str] = []
    stopping = asyncio.Event()

    def make(name):
        async def job_fn(ctx):
            runs.append(name)
            if len(runs) == 2:
                stopping.set()
            return {}

        return job_fn

    fake_jobs = (
        Job("eins", timedelta(hours=1), make("eins"), lambda ctx: NOW),
        Job("zwei", timedelta(hours=1), make("zwei"), lambda ctx: NOW),
        Job("spaeter", timedelta(hours=1), make("spaeter"), lambda ctx: NOW + timedelta(hours=5)),
    )
    monkeypatch.setattr(main, "JOBS", fake_jobs)
    monkeypatch.setattr(main, "TICK_SECONDS", 0.01)
    ctx = jobs.Context(settings=Settings(environment="test"), now=lambda: NOW)

    asyncio.run(asyncio.wait_for(main.run_forever(ctx, stopping), timeout=5))
    assert runs == ["eins", "zwei"]


# --- ATT&CK-Job (Schritt 6.1) ---------------------------------------------------


def test_the_attack_job_runs_only_on_request():
    assert main.ATTACK not in JOBS
    assert main.BY_NAME["attack"] is main.ATTACK


def test_the_report_is_only_for_the_attack_job(capsys):
    import pytest

    with pytest.raises(SystemExit):
        asyncio.run(main.main(["run", "statistik", "--bericht"]))
    assert "--bericht" in capsys.readouterr().err


def test_control_characters_cannot_steer_the_terminal():
    shown = main.printable("echo \x1b[2J\x1b]0;x\x07\r\nfertig\x00")
    assert "\x1b" not in shown and "\x07" not in shown and "\r" not in shown and "\x00" not in shown
    assert "\\x1b[2J" in shown
    assert shown.isprintable()


def test_long_commands_are_cut_in_the_report():
    shown = main.printable("x" * 500)
    assert len(shown) == main.REPORT_WIDTH and shown.endswith("…")


def test_the_report_names_counts_and_share():
    text = main.format_report(
        {"befehle": 10, "ohne_technik": 4, "haeufigste": [("ls -la", 3), ("echo \x1b[31m", 1)]}
    )
    lines = text.splitlines()
    assert lines[0] == "Befehle gesamt: 10, ohne ATT&CK-Technik: 4 (40%)"
    assert lines[2].split() == ["3", "ls", "-la"]
    assert "\x1b" not in text


def test_an_empty_report_does_not_divide_by_zero():
    assert "(–)" in main.format_report({"befehle": 0, "ohne_technik": 0, "haeufigste": []})
