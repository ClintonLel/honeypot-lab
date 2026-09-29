"""Prüft GET /health und das Anfrage-Log."""

from __future__ import annotations

import json
import logging

from app.main import database_reachable


def test_health_is_ok_when_the_database_answers(app_client):
    app_client.app.dependency_overrides[database_reachable] = lambda: True
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_is_503_when_the_database_is_gone(app_client):
    app_client.app.dependency_overrides[database_reachable] = lambda: False
    response = app_client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error"}


def test_schema_page_is_closed_in_production(monkeypatch):
    """Die API steht im Internet, das Schema muss dort niemand sehen."""
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    for key, value in {
        "ENVIRONMENT": "production",
        "POSTGRES_PASSWORD": "p" * 64,
        "IP_HMAC_KEY": "k" * 64,
        "INGEST_TOKEN": "i" * 64,
    }.items():
        monkeypatch.setenv(key, value)
    try:
        app = create_app()
        assert app.docs_url is None
        assert app.openapi_url is None
    finally:
        get_settings.cache_clear()


def test_request_log_has_no_client_address(app_client, caplog):
    """Uvicorns Access-Log ist aus, unser eigenes Log kennt keine Adressen."""
    app_client.app.dependency_overrides[database_reachable] = lambda: True
    with caplog.at_level(logging.INFO, logger="lab.api"):
        app_client.get("/health")

    records = [r for r in caplog.records if r.getMessage() == "anfrage"]
    assert records, "die Anfrage wurde nicht geloggt"
    record = records[-1]
    assert record.path == "/health"
    assert record.status == 200
    fields = {k for k in record.__dict__ if not k.startswith("_")}
    assert not fields & {"client", "client_ip", "ip", "remote_addr"}


def test_log_formatter_writes_one_json_line():
    from app.logging import JsonFormatter

    record = logging.LogRecord("lab.api", logging.INFO, __file__, 1, "anfrage", None, None)
    record.path = "/health"
    line = JsonFormatter().format(record)
    assert "\n" not in line
    payload = json.loads(line)
    assert payload["msg"] == "anfrage"
    assert payload["path"] == "/health"
    assert payload["level"] == "INFO"
