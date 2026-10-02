"""POST /v1/chat/completions: das LLM-Gateway (Schritt 7.2, E-043).

Ohne Datenbank und ohne echten Anbieter: Das Gateway bekommt eine Attrappe
(``tests/llm_fakes.py``) und ein Ledger im Speicher. Die Anfragen baut
``tests/cowrie_llm.py`` exakt so wie Cowrie 3.0.14.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

import httpx2
import pytest

from decimal import Decimal

from app.config import PLACEHOLDER
from app.llm_gateway import Gateway, build_config, gateway_of
from app.llm_limits import Prices, estimate_micros
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


def test_a_spent_month_stops_with_503_without_calling_the_provider(llm):
    """Ein Budgetstopp ist ein Ausfall, kein Teil der Behandlung: 503, nicht 429."""
    client, make = llm
    upstream, ledger = ready(make, ledger=MemoryLedger(month=20_000_000))
    response = post(client, exec_request("id"))
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "server_error"
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert ledger.statuses == ["budget_exceeded"] and upstream.calls == 0


def test_a_spent_day_stops_with_503_without_calling_the_provider(llm):
    client, make = llm
    upstream, ledger = ready(make, ledger=MemoryLedger(month=5_000_000, day=2_000_000))
    response = post(client, exec_request("id"))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert ledger.statuses == ["budget_exceeded"] and upstream.calls == 0


def test_the_next_day_opens_again(llm):
    client, make = llm
    now = [NOW]
    upstream = Upstream()
    ledger = MemoryLedger(day=2_000_000)
    make(llm_settings(), ledger=ledger, upstream=upstream, clock=lambda: now[0])
    assert post(client, exec_request("id")).status_code == 503
    now[0] = NOW + timedelta(days=1)
    assert post(client, exec_request("id")).status_code == 200
    assert upstream.calls == 1


def test_the_budget_counts_the_calls_of_this_process(llm):
    client, make = llm
    # Jeder Aufruf kostet 1.005 µ€, das Tagesbudget reicht für zwei.
    upstream, ledger = ready(make, llm_budget_day_eur="0.002")
    codes = [post(client, exec_request("id")).status_code for _ in range(4)]
    assert codes == [200, 200, 503, 503]
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
        (lambda r: httpx2.Response(429, json={"error": {"code": "rate_limit_exceeded"}}), "upstream_limited"),
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


def raise_with(error_type):
    def reply(request):
        raise error_type("abbruch", request=request)

    return reply


def expected_estimate(body) -> int:
    chars = sum(len(m["content"]) for m in body["messages"])
    prices = Prices(input=Decimal("0.40"), cached_input=Decimal("0.10"), output=Decimal("1.60"))
    return estimate_micros(chars, 2048, prices)


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        (raise_with(httpx2.ReadError), "upstream_error"),
        (raise_with(httpx2.WriteError), "upstream_error"),
        (raise_with(httpx2.RemoteProtocolError), "upstream_error"),
        (raise_with(httpx2.DecodingError), "upstream_error"),
        (lambda r: httpx2.Response(200, content=b"x" * (1024 * 1024 + 10)), "upstream_error"),
        (raise_with(httpx2.ReadTimeout), "timeout"),
        (raise_with(httpx2.WriteTimeout), "timeout"),
    ],
)
def test_an_abort_after_sending_books_the_estimate(llm, reply, status):
    """Die Anfrage war unterwegs; der Anbieter kann abrechnen."""
    client, make = llm
    upstream, ledger = ready(make, upstream=Upstream(reply))
    body = exec_request("id")
    response = post(client, body)
    assert response.status_code == (504 if status == "timeout" else 502)
    [row] = ledger.rows
    assert row.status == status
    assert row.cost_micros == expected_estimate(body) > 0


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        (raise_with(httpx2.ConnectError), "upstream_error"),
        (raise_with(httpx2.ConnectTimeout), "timeout"),
        (raise_with(httpx2.PoolTimeout), "timeout"),
        (lambda r: httpx2.Response(500, json={"error": {"message": "intern"}}), "upstream_error"),
        (lambda r: httpx2.Response(401, json={"error": {"code": "invalid_api_key"}}), "upstream_error"),
    ],
)
def test_no_connection_or_an_error_answer_books_nothing(llm, reply, status):
    """Sonst leerte ein Ausfall des Anbieters das Tagesbudget und machte B stumm."""
    client, make = llm
    upstream, ledger = ready(make, upstream=Upstream(reply))
    response = post(client, exec_request("id"))
    assert response.status_code == (504 if status == "timeout" else 502)
    [row] = ledger.rows
    assert row.status == status
    assert row.cost_micros == 0


def test_an_unreachable_provider_does_not_empty_the_budget(llm):
    client, make = llm
    upstream, ledger = ready(make, upstream=Upstream(raise_with(httpx2.ConnectError)), llm_budget_day_eur="0.002")
    codes = {post(client, exec_request("id")).status_code for _ in range(20)}
    assert codes == {502}
    assert upstream.calls == 20


def test_a_provider_429_is_not_passed_on_as_429(llm):
    """429 heißt auf dem Sensor nur Minutengrenze."""
    client, make = llm
    limit = {"error": {"message": "limit", "code": "project_spend_limit_exceeded"}}
    upstream, ledger = ready(make, upstream=Upstream(lambda r: httpx2.Response(429, json=limit)))
    limited = post(client, exec_request("id"))
    assert limited.status_code == 502
    [row] = ledger.rows
    assert row.status == "upstream_limited"
    assert row.cost_micros == 0
    # Für den Sensor derselbe Rumpf wie bei jedem anderen Fehler beim Anbieter.
    upstream.reply = lambda r: httpx2.Response(500, json={"error": {"message": "intern"}})
    other = post(client, exec_request("id"))
    assert other.status_code == 502
    assert limited.json() == other.json()
    assert ledger.statuses == ["upstream_limited", "upstream_error"]


def test_only_the_minute_limit_answers_429(llm):
    client, make = llm
    clock = [100.0]
    upstream, ledger = Upstream(), MemoryLedger(day=1_999_000)
    make(llm_settings(llm_calls_per_minute=1), ledger=ledger, upstream=upstream, monotonic=lambda: clock[0])
    assert post(client, exec_request("id")).status_code == 200  # Tagesbudget danach erschöpft
    assert post(client, exec_request("id")).status_code == 503
    ledger2 = MemoryLedger()
    make(llm_settings(llm_calls_per_minute=1), ledger=ledger2, upstream=upstream, monotonic=lambda: clock[0])
    assert post(client, exec_request("id")).status_code == 200
    assert post(client, exec_request("id")).status_code == 429
    assert ledger.statuses == ["ok", "budget_exceeded"]
    assert ledger2.statuses == ["ok", "rate_limited"]


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


# --- Größte Anfrage von Cowrie (E-044) ------------------------------------------
#
# Cowrie 3.0.14 kürzt Befehle auf 4.096 Zeichen, schickt höchstens zehn
# Einträge Verlauf (davon höchstens fünf Antworten) und kodiert mit
# ensure_ascii. Die Antworten im Verlauf hat das Gateway selbst geliefert,
# also höchstens so lang, wie cap_reply sie durchlässt. Diese Anfragen dürfen
# weder an Caddy (1 MB) noch am Gateway scheitern.

from app.llm_gateway import MAX_REPLY_CHARS, MAX_REPLY_JSON_BYTES, cap_reply  # noqa: E402
from app.llm_request import MAX_BODY_BYTES as GATEWAY_MAX_BODY  # noqa: E402
from tests.cowrie_llm import MAX_COMMAND_LENGTH, PERSONA_MAX_CHARS  # noqa: E402

# request_body { max_size 1MB } in Caddy (E-021): 1 MB = 1.000.000 Byte.
CADDY_MAX_BODY = 1_000_000
# Außerhalb der BMP: 12 Byte je Zeichen mit ensure_ascii.
WIDE = "\U0001F600"


def largest_persona() -> str:
    """So lang wie erlaubt, mit Zeilenumbrüchen wie die echte (je 2 Byte als JSON)."""
    line = "x" * 79 + "\n"
    persona = line * (PERSONA_MAX_CHARS // len(line))
    return persona + "y" * (PERSONA_MAX_CHARS - len(persona))


def largest_command(char: str) -> str:
    # Ein Angreifer schickt 8.192 Zeichen, Cowrie kürzt vor dem Prompt.
    return (char * 8192)[:MAX_COMMAND_LENGTH]


def largest_interactive(char: str) -> dict:
    reply, _ = cap_reply(char * 100_000)
    history: list[str] = []
    for _ in range(5):
        history += [f"System: {reply}", f"User: {largest_command(char)}"]
    return interactive_request(history, template=largest_persona())


@pytest.mark.parametrize("char", ["a", WIDE])
def test_the_largest_exec_request_gets_through(llm, char):
    client, make = llm
    upstream, _ = ready(make)
    body = exec_request(largest_command(char), template=largest_persona())
    assert len(encode(body)) < CADDY_MAX_BODY
    response = post(client, body)
    assert response.status_code == 200
    assert upstream.calls == 1


@pytest.mark.parametrize("char", ["a", WIDE])
def test_the_largest_interactive_request_gets_through(llm, char):
    client, make = llm
    upstream, _ = ready(make)
    body = largest_interactive(char)
    assert len(body["messages"]) == 11
    assert len(encode(body)) < CADDY_MAX_BODY <= GATEWAY_MAX_BODY
    response = post(client, body)
    assert response.status_code == 200, response.text
    assert upstream.calls == 1


def test_an_empty_line_in_an_interactive_session_gets_through(llm):
    """Cowrie schickt auch eine leere Zeile ans Modell (Behandlung, E-044)."""
    client, make = llm
    upstream, _ = ready(make)
    response = post(client, interactive_request(["User: "]))
    assert response.status_code == 200
    assert upstream.payload()["messages"][-1] == {"role": "user", "content": ""}


def test_an_empty_exec_command_gets_through(llm):
    """Ohne Befehl nimmt Cowrie den interaktiven Prompt und hängt nichts an."""
    client, make = llm
    ready(make)
    assert post(client, exec_request("")).status_code == 200


@pytest.mark.parametrize(
    ("content", "expected_chars"),
    [
        ("a" * 20_000, MAX_REPLY_CHARS),
        (WIDE * 20_000, MAX_REPLY_JSON_BYTES // 12),
        ("\x00" * 20_000, MAX_REPLY_JSON_BYTES // 6),
    ],
)
def test_a_long_answer_is_cut_so_it_fits_back_into_the_history(llm, caplog, content, expected_chars):
    client, make = llm
    ready(make, upstream=Upstream(lambda r: httpx2.Response(200, json=completion(content))))
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        response = post(client, exec_request("cat /dev/urandom"))
    assert response.status_code == 200
    text = cowrie_reads(200, response.content)
    assert len(text) == expected_chars
    assert text == content[:expected_chars]
    assert response.json()["choices"][0]["finish_reason"] == "length"
    assert [r.gekuerzt for r in caplog.records if r.getMessage() == "llm"] == [True]


def test_a_normal_answer_is_not_cut(llm, caplog):
    client, make = llm
    ready(make)
    with caplog.at_level(logging.INFO, logger="lab.llm"):
        response = post(client, exec_request("uname -a"))
    assert cowrie_reads(200, response.content) == ANSWER
    assert response.json()["choices"][0]["finish_reason"] == "stop"
    assert [r.gekuerzt for r in caplog.records if r.getMessage() == "llm"] == [False]


def test_cap_reply_keeps_short_texts_and_counts_bytes_like_cowrie():
    import json

    assert cap_reply("hallo") == ("hallo", False)
    assert cap_reply("a" * MAX_REPLY_CHARS) == ("a" * MAX_REPLY_CHARS, False)
    cut, truncated = cap_reply("ä" * MAX_REPLY_CHARS)
    assert truncated
    assert len(json.dumps(cut)) - 2 <= MAX_REPLY_JSON_BYTES
    assert len(json.dumps(cut + "ä")) - 2 > MAX_REPLY_JSON_BYTES
