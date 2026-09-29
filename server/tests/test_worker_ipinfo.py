"""Prüft den Download der IPinfo-Lite-Datenbank, ohne Netz.

Ein gefälschter Server liefert Prüfsumme und Datei. Geprüft wird vor allem,
was bei Fehlern passiert: Die alte Datei muss dann unangetastet stehen bleiben,
denn die API liest sie in jedem Moment. Und das Token darf nirgends auftauchen,
weder im Ergebnis noch in Fehlermeldungen noch im Log.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import urllib.error
from hashlib import sha256
from pathlib import Path

import pytest

from app.config import Settings
from worker import jobs
from worker.main import IPINFO, run_job

TOKEN = "ipinfo-geheim-1234567890"
NEW = b"neue datenbank" * 100
OLD = b"alte datenbank"


class FakeServer:
    """Liefert Prüfsumme und Datei und merkt sich, was angefragt wurde."""

    def __init__(self, payload: bytes = NEW, checksum: str | None = "passend") -> None:
        self.payload = payload
        if checksum == "passend":
            checksum = sha256(payload).hexdigest()
        self.checksum = checksum
        self.requests: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.requests.append(url)
        assert f"token={TOKEN}" in url, "das Token gehört in die Anfrage"
        if url.startswith(jobs.CHECKSUM_URL):
            body = {"checksums": {"md5": "x", "sha1": "y"}}
            if self.checksum:
                body["checksums"]["sha256"] = self.checksum
            return io.BytesIO(json.dumps(body).encode())
        if url.startswith(jobs.LITE_URL):
            return io.BytesIO(self.payload)
        raise AssertionError(f"unerwartete Anfrage: {url.split('?')[0]}")

    @property
    def downloads(self) -> int:
        return sum(1 for url in self.requests if url.startswith(jobs.LITE_URL + "?"))


def context(tmp_path: Path, server: FakeServer, validator=None, token: str = TOKEN) -> jobs.Context:
    settings = Settings(
        environment="test",
        ipinfo_token=token,
        ipinfo_db_path=str(tmp_path / "ipinfo.mmdb"),
    )
    return jobs.Context(
        settings=settings,
        opener=server,
        validator=validator or (lambda path: None),
    )


def run(ctx: jobs.Context) -> dict:
    return asyncio.run(jobs.update_ipinfo(ctx))


# --- Normale Läufe ----------------------------------------------------------


def test_without_a_token_nothing_is_requested(tmp_path):
    server = FakeServer()
    result = run(context(tmp_path, server, token=""))
    assert result["status"] == "übersprungen"
    assert server.requests == []


def test_a_new_database_is_downloaded_checked_and_put_in_place(tmp_path):
    server = FakeServer()
    checked: list[Path] = []
    result = run(context(tmp_path, server, validator=checked.append))

    assert result["status"] == "aktualisiert"
    assert result["pruefsumme"] == "geprüft"
    assert (tmp_path / "ipinfo.mmdb").read_bytes() == NEW
    # Geprüft wurde die Zwischendatei, bevor sie an ihren Platz kam.
    assert checked and checked[0].name.endswith(".part")
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob(".*.part"))


def test_an_unchanged_database_is_not_downloaded_again(tmp_path):
    """IPinfo erlaubt 10 Downloads am Tag, die Prüfsumme zählt nicht mit."""
    (tmp_path / "ipinfo.mmdb").write_bytes(NEW)
    server = FakeServer()
    result = run(context(tmp_path, server))
    assert result["status"] == "unverändert"
    assert server.downloads == 0


def test_without_a_checksum_the_file_is_still_checked(tmp_path):
    server = FakeServer(checksum=None)
    checked: list[Path] = []
    result = run(context(tmp_path, server, validator=checked.append))
    assert result["status"] == "aktualisiert"
    assert result["pruefsumme"] == "nicht verfügbar"
    assert checked


# --- Fehler lassen die alte Datei stehen ------------------------------------


def test_a_wrong_checksum_keeps_the_old_file(tmp_path):
    target = tmp_path / "ipinfo.mmdb"
    target.write_bytes(OLD)
    server = FakeServer(checksum="0" * 64)

    with pytest.raises(jobs.DownloadError, match="Prüfsumme"):
        run(context(tmp_path, server))
    assert target.read_bytes() == OLD
    assert not list(tmp_path.glob(".*.part"))


def test_a_file_that_does_not_open_keeps_the_old_file(tmp_path):
    target = tmp_path / "ipinfo.mmdb"
    target.write_bytes(OLD)

    def broken(path: Path) -> None:
        raise jobs.DownloadError("Datei lässt sich nicht lesen")

    with pytest.raises(jobs.DownloadError):
        run(context(tmp_path, FakeServer(), validator=broken))
    assert target.read_bytes() == OLD
    assert not list(tmp_path.glob(".*.part"))


def test_an_oversized_download_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_DOWNLOAD_BYTES", 100)
    monkeypatch.setattr(jobs, "CHUNK", 10)
    with pytest.raises(jobs.DownloadError, match="größer"):
        run(context(tmp_path, FakeServer(payload=b"x" * 1000, checksum=None)))
    assert not (tmp_path / "ipinfo.mmdb").exists()


def test_a_directory_without_write_access_fails_clearly(tmp_path):
    readonly = tmp_path / "nur-lesen"
    readonly.mkdir()
    readonly.chmod(0o500)
    settings = Settings(environment="test", ipinfo_token=TOKEN, ipinfo_db_path=str(readonly / "ipinfo.mmdb"))
    ctx = jobs.Context(settings=settings, opener=FakeServer(), validator=lambda path: None)
    try:
        with pytest.raises(jobs.DownloadError, match="nicht beschreibbar"):
            run(ctx)
    finally:
        readonly.chmod(0o700)


# --- Das Token bleibt geheim ------------------------------------------------


def test_http_errors_do_not_reveal_the_url(monkeypatch):
    """urllib hängt die URL an die Ausnahme. Unsere Meldung darf sie nicht tragen."""
    url = jobs.with_token(jobs.LITE_URL, TOKEN)

    def refuse(request, timeout):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(jobs.urllib.request, "urlopen", refuse)
    with pytest.raises(jobs.DownloadError) as exc:
        jobs.default_opener(url, 5)
    assert str(exc.value) == "HTTP 401"
    assert TOKEN not in repr(exc.value)
    assert exc.value.__cause__ is None


def test_connection_errors_do_not_reveal_the_url(monkeypatch):
    def unreachable(request, timeout):
        raise urllib.error.URLError(f"nicht erreichbar: {request.full_url}")

    monkeypatch.setattr(jobs.urllib.request, "urlopen", unreachable)
    with pytest.raises(jobs.DownloadError) as exc:
        jobs.default_opener(jobs.with_token(jobs.LITE_URL, TOKEN), 5)
    assert TOKEN not in str(exc.value)


def test_the_token_is_neither_in_the_result_nor_in_the_log(tmp_path, caplog):
    ctx = context(tmp_path, FakeServer())
    with caplog.at_level(logging.DEBUG):
        ok = asyncio.run(run_job(IPINFO, ctx))
    assert ok
    everything = " ".join(
        f"{record.getMessage()} {record.__dict__}" for record in caplog.records
    )
    assert "job fertig" in everything
    assert TOKEN not in everything


def test_a_failed_download_is_logged_without_the_token(tmp_path, caplog):
    ctx = context(tmp_path, FakeServer(checksum="0" * 64))
    with caplog.at_level(logging.DEBUG):
        ok = asyncio.run(run_job(IPINFO, ctx))
    assert not ok
    failed = [r for r in caplog.records if r.getMessage() == "job fehlgeschlagen"]
    assert failed and failed[0].fehler == "Prüfsumme stimmt nicht"
    assert all(TOKEN not in str(r.__dict__) for r in caplog.records)


def test_the_checksum_is_found_wherever_it_is():
    assert jobs.find_sha256({"sha256": "ABC"}) == "abc"
    assert jobs.find_sha256({"checksums": {"SHA256": "def"}}) == "def"
    assert jobs.find_sha256({"checksums": {"md5": "x"}}) is None
    assert jobs.find_sha256(["kein", "objekt"]) is None
