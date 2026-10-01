"""POST /v1/chat/completions: das LLM-Gateway (Schritt 7.2, E-043).

Ohne Datenbank und ohne echten Anbieter: Das Gateway bekommt eine Attrappe
(``tests/llm_fakes.py``) und ein Ledger im Speicher. Die Anfragen baut
``tests/cowrie_llm.py`` exakt so wie Cowrie 3.0.14.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

import httpx2
import pytest

from app.config import PLACEHOLDER
from app.llm_gateway import Gateway, build_config, gateway_of
from app.llm_request import persona_sha256
from tests.cowrie_llm import (
    PERSONA,
    SENSOR_IP,
    SENSOR_IP6,
    cowrie_reads,
    encode,
    exec_request,
    interactive_request,
)
from tests.llm_fakes import (
    ANSWER,
    API_KEY,
    GATEWAY_TOKEN,
    MODEL,
    NOW,
    TEST_SECRET,
    MemoryLedger,
    Upstream,
    auth,
    completion,
    llm_settings,
)

PATH = "/v1/chat/completions"
PERSONA_HASH = persona_sha256(PERSONA.format(ip=SENSOR_IP, ip6=SENSOR_IP6))


@pytest.fixture
def llm(monkeypatch):
    """Die App mit einem Gateway nach Wahl des Tests.

    ``make(...)`` baut das Gateway und hängt es per ``dependency_overrides``
    ein. Rückgabe: (TestClient, make).
    """
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", TEST_SECRET)
    monkeypatch.setenv("IP_HMAC_KEY", TEST_SECRET)
    monkeypatch.setenv("INGEST_TOKEN", TEST_SECRET)
    app = create_app()
    built: list[Gateway] = []

    def make(settings=None, *, ledger=None, upstream=None, clock=None, monotonic=time.monotonic):
        gateway = Gateway.from_settings(
            settings or llm_settings(),
            ledger=ledger if ledger is not None else MemoryLedger(),
            clock=clock or (lambda: NOW),
            monotonic=monotonic,
            transport=(upstream or Upstream()).transport,
        )
        app.dependency_overrides[gateway_of] = lambda: gateway
        built.append(gateway)
        return gateway

    with TestClient(app) as client:
        yield client, make
        for gateway in built:
            client.portal.call(gateway.aclose)
    get_settings.cache_clear()


def post(client, body, token: str | None = GATEWAY_TOKEN, **kwargs):
    headers = auth(token) if token is not None else {}
    data = body if isinstance(body, bytes) else encode(body)
    return client.post(PATH, content=data, headers=headers, **kwargs)


def ready(make, **overrides):
    """Gateway mit Attrappe und Ledger; gibt beides mit zurück."""
    upstream = overrides.pop("upstream", None) or Upstream()
    ledger = overrides.pop("ledger", None) or MemoryLedger()
    settings = llm_settings(**overrides)
    make(settings, ledger=ledger, upstream=upstream)
    return upstream, ledger


# --- Token ---------------------------------------------------------------------


def test_without_a_token_nothing_is_written_and_nothing_is_called(llm):
    client, make = llm
    upstream, ledger = ready(make)
    response = post(client, exec_request("id"), token=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    assert ledger.rows == [] and upstream.calls == 0


def test_a_wrong_token_is_refused_the_same_way(llm):
    client, make = llm
    upstream, ledger = ready(make)
    without = post(client, exec_request("id"), token=None)
    wrong = post(client, exec_request("id"), token="f" * 64)
    other_scheme = client.post(PATH, content=encode(exec_request("id")), headers={"Authorization": f"Basic {GATEWAY_TOKEN}"})
    assert wrong.status_code == other_scheme.status_code == 401
    assert without.json() == wrong.json() == other_scheme.json()
    assert ledger.rows == [] and upstream.calls == 0


def test_the_ingest_token_does_not_open_the_gateway(llm):
    client, make = llm
    upstream, ledger = ready(make)
    assert post(client, exec_request("id"), token=TEST_SECRET).status_code == 401


def test_a_rejected_token_is_logged_without_its_value(llm, caplog):
    client, make = llm
    ready(make)
    wrong = "w" * 64
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        post(client, exec_request("id"), token=wrong)
    records = [r for r in caplog.records if r.getMessage() == "llm-gateway abgelehnt"]
    assert len(records) == 1
    assert records[0].laenge == 64
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert wrong not in text and GATEWAY_TOKEN not in text


# --- 503: abgeschaltet oder nicht konfiguriert ---------------------------------


@pytest.mark.parametrize("token", ["", PLACEHOLDER, "zu-kurz"])
def test_without_a_usable_gateway_token_the_gateway_is_unavailable(llm, token):
    client, make = llm
    upstream, ledger = ready(make, llm_gateway_token=token)
    response = post(client, exec_request("id"), token=token or "x")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    assert ledger.rows == [] and upstream.calls == 0


def test_switched_off_the_gateway_answers_503_and_writes_disabled(llm):
    client, make = llm
    upstream, ledger = ready(make, llm_gateway_enabled=False)
    response = post(client, exec_request("id"))
    assert response.status_code == 503
    assert ledger.statuses == ["disabled"]
    assert ledger.rows[0].model == MODEL
    assert upstream.calls == 0


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("llm_api_key", ""),
        ("llm_api_key", PLACEHOLDER),
        ("llm_api_key", "sk-zu-kurz"),
        ("llm_base_url", ""),
        ("llm_base_url", "http://llm.example.test/v1"),
        ("llm_base_url", "https://user:pw@llm.example.test/v1"),
        ("llm_model", ""),
        ("llm_model", "m" * 65),
        ("llm_max_tokens", 0),
        ("llm_max_tokens", "viele"),
        ("llm_max_tokens_param", "max_output_tokens"),
        ("llm_temperature", 2.5),
        ("llm_temperature", "nan"),
        ("llm_timeout_seconds", 60),
        ("llm_price_input_eur", ""),
        ("llm_price_input_eur", "0"),
        ("llm_price_cached_input_eur", "-0.1"),
        ("llm_price_output_eur", "0,60"),
        ("llm_budget_month_eur", ""),
        ("llm_budget_day_eur", "0"),
        ("llm_calls_per_minute", 0),
        ("llm_prompt_sha256", "abc"),
    ],
)
def test_incomplete_configuration_means_503(llm, setting, value):
    client, make = llm
    upstream, ledger = ready(make, **{setting: value})
    response = post(client, exec_request("id"))
    assert response.status_code == 503
    assert ledger.statuses == ["disabled"]
    assert upstream.calls == 0


def test_the_startup_log_names_missing_variables_but_no_values(caplog):
    settings = llm_settings(llm_api_key=PLACEHOLDER, llm_budget_day_eur="")
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        Gateway.from_settings(settings, ledger=MemoryLedger())
    record = next(r for r in caplog.records if r.getMessage() == "llm-gateway aus")
    assert record.fehlt == ["LLM_API_KEY", "LLM_BUDGET_DAY_EUR"]
    assert GATEWAY_TOKEN not in str(record.__dict__)


def test_a_complete_configuration_is_reported_ready(caplog):
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        Gateway.from_settings(llm_settings(), ledger=MemoryLedger())
    record = next(r for r in caplog.records if r.getMessage() == "llm-gateway bereit")
    assert record.model == MODEL
    assert API_KEY not in str(record.__dict__) and GATEWAY_TOKEN not in str(record.__dict__)


def test_build_config_derives_the_url_and_the_budget_in_micros():
    config, problems = build_config(llm_settings(llm_base_url="https://llm.example.test/v1/"))
    assert problems == []
    assert config.url == "https://llm.example.test/v1/chat/completions"
    assert (config.budget_month_micros, config.budget_day_micros) == (20_000_000, 2_000_000)


def test_the_real_app_starts_with_an_unconfigured_gateway(app_client):
    """Ohne LLM-Variablen läuft die API; nur das Gateway antwortet mit 503."""
    response = app_client.post(PATH, content=encode(exec_request("id")), headers=auth())
    assert response.status_code == 503
    assert app_client.post("/ingest", json=[]).status_code == 401


# --- Was beim Anbieter ankommt -------------------------------------------------


def test_model_limits_and_temperature_come_from_the_gateway(llm):
    client, make = llm
    upstream, _ = ready(make)
    body = exec_request("uname -a", model="teures-modell", max_tokens=99_999, temperature=1.9)
    assert post(client, body).status_code == 200
    sent = upstream.payload()
    assert sent["model"] == MODEL
    assert sent["max_completion_tokens"] == 2048
    assert "max_tokens" not in sent
    assert sent["temperature"] == 0.0
    assert set(sent) == {"model", "messages", "max_completion_tokens", "temperature"}


def test_max_tokens_can_be_sent_under_its_old_name(llm):
    client, make = llm
    upstream, _ = ready(make, llm_max_tokens_param="max_tokens", llm_max_tokens=900)
    post(client, exec_request("id"))
    assert upstream.payload()["max_tokens"] == 900
    assert "max_completion_tokens" not in upstream.payload()


def test_the_messages_reach_the_provider_unchanged(llm):
    client, make = llm
    upstream, _ = ready(make)
    body = interactive_request(["User: ls", "System: bin  etc", "User: cat /etc/hostname"])
    post(client, body)
    assert upstream.payload()["messages"] == body["messages"]


def test_the_provider_gets_the_real_key_and_nothing_from_the_sensor(llm):
    client, make = llm
    upstream, _ = ready(make)
    post(client, exec_request("id"))
    request = upstream.requests[0]
    assert str(request.url) == "https://llm.example.test/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert GATEWAY_TOKEN not in str(request.headers)


# --- Antwort -------------------------------------------------------------------


def test_cowrie_reads_the_answer(llm):
    client, make = llm
    upstream, ledger = ready(make)
    response = post(client, exec_request("uname -a"))
    assert response.status_code == 200
    assert cowrie_reads(response.status_code, response.content) == ANSWER
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == MODEL
    assert body["choices"][0]["finish_reason"] == "stop"
    assert set(body) == {"id", "object", "created", "model", "choices"}
    assert "fp_anbieter" not in response.text and "anbieter-modell" not in response.text


def test_an_answer_without_content_is_empty_text(llm):
    client, make = llm
    ready(make, upstream=Upstream(lambda r: httpx2.Response(200, json=completion(None))))
    response = post(client, exec_request("id"))
    assert response.status_code == 200
    assert cowrie_reads(200, response.content) == ""


def test_unknown_finish_reasons_become_stop(llm):
    client, make = llm
    ready(make, upstream=Upstream(lambda r: httpx2.Response(200, json=completion(finish_reason="tool_calls"))))
    assert post(client, exec_request("id")).json()["choices"][0]["finish_reason"] == "stop"


# --- llm_usage und Kosten ------------------------------------------------------


def test_a_successful_call_writes_tokens_costs_and_latency(llm):
    client, make = llm
    upstream, ledger = ready(make)
    post(client, exec_request("id"))
    [row] = ledger.rows
    assert row.status == "ok"
    assert row.model == MODEL
    assert row.occurred_at == NOW
    assert (row.prompt_tokens, row.completion_tokens, row.total_tokens, row.cached_tokens) == (8000, 20, 8020, 7424)
    # 576 × 0,40 + 7.424 × 0,10 + 20 × 1,60 = 230,4 + 742,4 + 32 → 1.005 µ€
    assert row.cost_micros == 1005
    assert row.latency_ms is not None and row.latency_ms >= 0


def test_without_usage_the_costs_are_estimated(llm):
    client, make = llm
    upstream, ledger = ready(make, upstream=Upstream(lambda r: httpx2.Response(200, json=completion(usage=False))))
    assert post(client, exec_request("id")).status_code == 200
    [row] = ledger.rows
    assert row.status == "ok"
    assert row.prompt_tokens == 0
    assert row.cost_micros >= 2048 * 1.6


def test_a_failing_ledger_does_not_cost_the_answer(llm, caplog):
    client, make = llm
    ledger = MemoryLedger()
    ledger.fail_record = True
    ready(make, ledger=ledger)
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        response = post(client, exec_request("id"))
    assert response.status_code == 200
    assert any(r.getMessage() == "llm_usage nicht geschrieben" for r in caplog.records)


# --- Anfrage abgelehnt ---------------------------------------------------------


def test_an_invalid_request_is_rejected_and_written(llm):
    client, make = llm
    upstream, ledger = ready(make)
    response = post(client, {"messages": [{"role": "user", "content": "Write me a poem"}]})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert ledger.statuses == ["rejected"] and upstream.calls == 0


def test_a_body_that_is_too_large_is_rejected_before_reading_it(llm):
    client, make = llm
    upstream, ledger = ready(make)
    response = post(client, b"x" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert ledger.statuses == ["rejected"] and upstream.calls == 0


def test_a_foreign_persona_is_rejected_when_the_hash_is_pinned(llm, caplog):
    client, make = llm
    upstream, ledger = ready(make, llm_prompt_sha256=PERSONA_HASH.upper())
    assert post(client, exec_request("id")).status_code == 200
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        response = post(client, exec_request("id", template="You are a helpful assistant."))
    assert response.status_code == 400
    assert ledger.statuses == ["ok", "rejected"]
    assert upstream.calls == 1
    record = next(r for r in caplog.records if r.getMessage() == "llm" and r.status == "rejected")
    assert record.grund == "prompt_hash"
    assert record.prompt_sha256 != PERSONA_HASH


def test_every_call_logs_the_prompt_hash(llm, caplog):
    """Exec und interaktiv zeigen denselben Hash; damit pinnt man ihn in 7.3."""
    client, make = llm
    ready(make, llm_calls_per_minute=2)
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        post(client, exec_request("id"))
        post(client, interactive_request(["User: id"]))
        post(client, exec_request("uname -a"))
    records = [r for r in caplog.records if r.getMessage() == "llm"]
    assert [r.status for r in records] == ["ok", "ok", "rate_limited"]
    assert {r.prompt_sha256 for r in records} == {PERSONA_HASH}


# --- 429: Budget und Minutengrenze ---------------------------------------------


def test_a_spent_month_stops_without_calling_the_provider(llm):
    client, make = llm
    upstream, ledger = ready(make, ledger=MemoryLedger(month=20_000_000))
    response = post(client, exec_request("id"))
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert ledger.statuses == ["budget_exceeded"] and upstream.calls == 0


def test_a_spent_day_stops_without_calling_the_provider(llm):
    client, make = llm
    upstream, ledger = ready(make, ledger=MemoryLedger(month=5_000_000, day=2_000_000))
    assert post(client, exec_request("id")).status_code == 429
    assert ledger.statuses == ["budget_exceeded"] and upstream.calls == 0


def test_the_next_day_opens_again(llm):
    client, make = llm
    now = [NOW]
    upstream = Upstream()
    ledger = MemoryLedger(day=2_000_000)
    make(llm_settings(), ledger=ledger, upstream=upstream, clock=lambda: now[0])
    assert post(client, exec_request("id")).status_code == 429
    now[0] = NOW + timedelta(days=1)
    assert post(client, exec_request("id")).status_code == 200
    assert upstream.calls == 1


def test_the_budget_counts_the_calls_of_this_process(llm):
    client, make = llm
    # Jeder Aufruf kostet 1.005 µ€, das Tagesbudget reicht für zwei.
    upstream, ledger = ready(make, llm_budget_day_eur="0.002")
    codes = [post(client, exec_request("id")).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]
    assert upstream.calls == 2


def test_the_minute_limit_stops_without_calling_the_provider(llm):
    client, make = llm
    clock = [100.0]
    upstream, ledger = Upstream(), MemoryLedger()
    make(llm_settings(llm_calls_per_minute=2), ledger=ledger, upstream=upstream, monotonic=lambda: clock[0])
    assert [post(client, exec_request("id")).status_code for _ in range(2)] == [200, 200]
    limited = post(client, exec_request("id"))
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1
    assert upstream.calls == 2
    assert ledger.statuses == ["ok", "ok", "rate_limited"]
    clock[0] += 60
    assert post(client, exec_request("id")).status_code == 200


def test_an_unreadable_budget_fails_closed(llm):
    client, make = llm
    ledger = MemoryLedger()
    ledger.fail_spent = True
    upstream, _ = ready(make, ledger=ledger)
    assert post(client, exec_request("id")).status_code == 503
    assert upstream.calls == 0
    ledger.fail_spent = False
    assert post(client, exec_request("id")).status_code == 200


# --- Fehler beim Anbieter ------------------------------------------------------


def test_a_slow_provider_gives_504_with_estimated_costs(llm):
    client, make = llm
    upstream, ledger = ready(make, upstream=Upstream(delay=5), llm_timeout_seconds=1)
    started = time.perf_counter()
    response = post(client, exec_request("id"))
    assert time.perf_counter() - started < 3
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"
    [row] = ledger.rows
    assert row.status == "timeout"
    assert row.prompt_tokens == 0
    assert row.cost_micros >= 2048 * 1.6
    assert row.latency_ms >= 900


def raise_connect(request):
    raise httpx2.ConnectError("verbindung abgelehnt", request=request)


def raise_read_timeout(request):
    raise httpx2.ReadTimeout("lesen dauert", request=request)


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        (lambda r: httpx2.Response(500, json={"error": {"message": "intern"}}), "upstream_error"),
        (lambda r: httpx2.Response(429, json={"error": {"code": "rate_limit_exceeded"}}), "upstream_error"),
        (lambda r: httpx2.Response(401, json={"error": {"code": "invalid_api_key"}}), "upstream_error"),
        (lambda r: httpx2.Response(200, content=b"<html>gateway</html>"), "upstream_error"),
        (lambda r: httpx2.Response(200, json={"choices": []}), "upstream_error"),
        (lambda r: httpx2.Response(200, json=completion(content=["teil"])), "upstream_error"),
        (lambda r: httpx2.Response(200, content=b"x" * (1024 * 1024 + 10)), "upstream_error"),
        (raise_connect, "upstream_error"),
        (raise_read_timeout, "timeout"),
    ],
)
def test_provider_failures_map_to_502_or_504(llm, reply, status):
    client, make = llm
    upstream, ledger = ready(make, upstream=Upstream(reply))
    response = post(client, exec_request("id"))
    assert response.status_code == (504 if status == "timeout" else 502)
    assert ledger.statuses == [status]
    assert upstream.calls == 1


def test_a_provider_429_is_not_passed_on_as_429(llm):
    """V3: 429 heißt auf dem Sensor nur „Grenze des Gateways“."""
    client, make = llm
    ready(make, upstream=Upstream(lambda r: httpx2.Response(429, json={"error": {"message": "slow down"}})))
    assert post(client, exec_request("id")).status_code == 502


def test_usage_on_a_broken_answer_still_counts(llm):
    client, make = llm
    broken = completion()
    broken["choices"] = []
    upstream, ledger = ready(make, upstream=Upstream(lambda r: httpx2.Response(200, json=broken)))
    post(client, exec_request("id"))
    assert ledger.rows[0].status == "upstream_error"
    assert ledger.rows[0].cost_micros == 1005


# --- Kein Inhalt in Logs und Antworten -----------------------------------------

MARKER = "MARKE-7f3a9c"


def all_log_text(caplog) -> str:
    return "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)


@pytest.mark.parametrize(
    "reply",
    [
        lambda r: httpx2.Response(200, json=completion(f"{MARKER} antwort")),
        lambda r: httpx2.Response(500, text=f"interner Fehler bei {MARKER}"),
        lambda r: httpx2.Response(400, json={"error": {"message": f"bad request: {MARKER}"}}),
        lambda r: httpx2.Response(200, text=f"kein json {MARKER}"),
        lambda r: (_ for _ in ()).throw(httpx2.ConnectError(f"fehler {MARKER}", request=r)),
    ],
)
def test_no_content_reaches_the_log(llm, caplog, reply):
    client, make = llm
    ready(make, upstream=Upstream(reply))
    history = [f"User: echo {MARKER}", f"System: {MARKER}", f"User: cat {MARKER}"]
    with caplog.at_level(logging.DEBUG):
        post(client, exec_request(f"wget hxxp://{MARKER}/x.sh", template=f"{MARKER} {PERSONA}"))
        post(client, interactive_request(history))
        post(client, {"messages": [{"role": "system", "content": MARKER}]})
        post(client, {"messages": [{"role": "user", "content": MARKER}], "stream": MARKER})
    statuses = [r.status for r in caplog.records if r.getMessage() == "llm"]
    assert len(statuses) == 4 and statuses.count("rejected") == 2
    text = all_log_text(caplog)
    assert MARKER not in text
    assert API_KEY not in text and GATEWAY_TOKEN not in text


@pytest.mark.parametrize(
    "reply",
    [
        lambda r: httpx2.Response(500, text=f"interner Fehler bei {MARKER} {r.headers['authorization']}"),
        lambda r: httpx2.Response(401, json={"error": {"message": f"Incorrect API key: {API_KEY}"}}),
        lambda r: (_ for _ in ()).throw(httpx2.ConnectError(f"{MARKER} {API_KEY}", request=r)),
    ],
)
def test_errors_from_the_provider_are_not_passed_on(llm, reply):
    client, make = llm
    ready(make, upstream=Upstream(reply))
    response = post(client, exec_request("id"))
    assert response.status_code == 502
    assert MARKER not in response.text
    assert API_KEY not in response.text
    assert response.json()["error"]["message"] == "Anbieter nicht verfügbar"


def test_an_unexpected_error_gives_500_without_traceback(llm, caplog, monkeypatch):
    client, make = llm
    gateway = make(llm_settings(), ledger=MemoryLedger(), upstream=Upstream())

    async def boom(*args, **kwargs):
        raise RuntimeError(f"kaputt {MARKER}")

    monkeypatch.setattr(gateway, "handle", boom)
    with caplog.at_level(logging.DEBUG):
        response = post(client, exec_request("id"))
    assert response.status_code == 500
    assert MARKER not in response.text
    assert MARKER not in all_log_text(caplog)
    assert all(r.exc_info is None for r in caplog.records)
