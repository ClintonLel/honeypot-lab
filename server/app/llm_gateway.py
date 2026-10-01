"""POST /v1/chat/completions: das LLM-Gateway für cowrie-b (Schritt 7.2, E-043).

cowrie-b ruft nie den Anbieter direkt, sondern diesen Endpunkt im
OpenAI-Format. Das Gateway prüft Token und Anfrage, setzt Modell und Grenzen
aus der eigenen Konfiguration durch, leitet an einen OpenAI-kompatiblen
Anbieter weiter und schreibt jede Anfrage mit gültigem Token in
``llm_usage``. Der echte API-Key steht nur in der ``.env`` des Hauptservers
(E-008).

Kein Inhalt in Logs: weder Prompt noch Antwort noch Teile davon, auch nicht
bei Fehlern. Bei Exec steht der Befehl des Angreifers im System-Prompt.
Fehler gehen im OpenAI-Format mit neutralem Text zurück, nie mit Details aus
der Antwort des Anbieters: Cowrie schreibt den Fehlertext in sein Log.

Reihenfolge je Anfrage (E-043):

1. Token nicht konfiguriert: 503, keine Zeile (das Token ist nicht prüfbar).
2. Token fehlt oder falsch: 401, keine Zeile, nur eine Logzeile ohne Inhalt.
3. Gateway abgeschaltet oder unvollständig konfiguriert: 503, ``disabled``.
4. Rumpf zu groß: 413, Anfrage ungültig: 400, beides ``rejected``.
5. Budget erreicht: 429 ``budget_exceeded``, Minutengrenze: 429
   ``rate_limited``. Der Anbieter wird nicht gerufen.
6. Anbieter: Zeitüberschreitung 504 ``timeout``, sonstiger Fehler 502
   ``upstream_error``, Erfolg 200 ``ok``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import bearer, rejection_fields, token_matches
from app.config import Settings, secret_problem
from app.llm_limits import (
    Budget,
    CallWindow,
    Prices,
    Usage,
    cost_micros,
    estimate_micros,
    parse_usage,
)
from app.llm_request import MAX_BODY_BYTES, CheckedRequest, RequestRejected, parse_request
from app.models import LlmUsage

logger = logging.getLogger("lab.llm")
router = APIRouter()

# Obergrenze für die Antwort des Anbieters, wie Cowries max_response_size.
# Gemessen nach dem Entpacken, ein komprimierter Brocken bläht sich nicht auf.
MAX_UPSTREAM_BYTES = 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 5.0
# Grenzen für die Werte aus der Konfiguration.
MAX_TOKENS_RANGE = (1, 16_384)
TEMPERATURE_RANGE = (0.0, 2.0)
TIMEOUT_RANGE = (1.0, 55.0)
CALLS_PER_MINUTE_RANGE = (1, 10_000)
MAX_TOKENS_PARAMS = ("max_completion_tokens", "max_tokens")
FINISH_REASONS = ("stop", "length", "content_filter")
# Breite der Spalte llm_usage.model.
MAX_MODEL_CHARS = 64


# --- Konfiguration ---------------------------------------------------------------


@dataclass(frozen=True)
class GatewayConfig:
    """Geprüfte Einstellungen. Der Key bleibt ein ``SecretStr``."""

    api_key: SecretStr
    url: str
    model: str
    max_tokens: int
    max_tokens_param: str
    temperature: float
    timeout_seconds: float
    prices: Prices
    budget_month_micros: int
    budget_day_micros: int
    calls_per_minute: int
    prompt_sha256: str


def _within(value: Any, bounds: tuple[Any, Any]) -> bool:
    # Auch NaN fällt hier durch: Jeder Vergleich mit NaN ist falsch.
    return value is not None and bounds[0] <= value <= bounds[1]


def _positive(value: Decimal | None) -> bool:
    return value is not None and value.is_finite() and value > 0


def _usable_url(url: str) -> bool:
    """Nur https, mit Host, ohne Zugangsdaten, Abfrage oder Anker in der URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and "@" not in parts.netloc
        and not parts.query
        and not parts.fragment
    )


def build_config(settings: Settings) -> tuple[GatewayConfig | None, list[str]]:
    """Prüft die Einstellungen des Gateways.

    Gibt die Konfiguration zurück oder ``None`` und die Namen der Variablen,
    die fehlen oder nicht passen. Nie die Werte.
    """
    problems: list[str] = []
    if secret_problem(settings.llm_gateway_token.get_secret_value()):
        problems.append("LLM_GATEWAY_TOKEN")
    if secret_problem(settings.llm_api_key.get_secret_value()):
        problems.append("LLM_API_KEY")
    if not _usable_url(settings.llm_base_url):
        problems.append("LLM_BASE_URL")
    model = settings.llm_model.strip()
    if not model or len(model) > MAX_MODEL_CHARS:
        problems.append("LLM_MODEL")
    if not _within(settings.llm_max_tokens, MAX_TOKENS_RANGE):
        problems.append("LLM_MAX_TOKENS")
    if settings.llm_max_tokens_param not in MAX_TOKENS_PARAMS:
        problems.append("LLM_MAX_TOKENS_PARAM")
    if not _within(settings.llm_temperature, TEMPERATURE_RANGE):
        problems.append("LLM_TEMPERATURE")
    if not _within(settings.llm_timeout_seconds, TIMEOUT_RANGE):
        problems.append("LLM_TIMEOUT_SECONDS")
    if not _positive(settings.llm_price_input_eur):
        problems.append("LLM_PRICE_INPUT_EUR")
    cached = settings.llm_price_cached_input_eur
    if cached is None or not cached.is_finite() or cached < 0:
        problems.append("LLM_PRICE_CACHED_INPUT_EUR")
    if not _positive(settings.llm_price_output_eur):
        problems.append("LLM_PRICE_OUTPUT_EUR")
    if not _positive(settings.llm_budget_month_eur):
        problems.append("LLM_BUDGET_MONTH_EUR")
    if not _positive(settings.llm_budget_day_eur):
        problems.append("LLM_BUDGET_DAY_EUR")
    if not _within(settings.llm_calls_per_minute, CALLS_PER_MINUTE_RANGE):
        problems.append("LLM_CALLS_PER_MINUTE")
    pinned = settings.llm_prompt_sha256.strip().lower()
    if pinned and (len(pinned) != 64 or any(c not in "0123456789abcdef" for c in pinned)):
        problems.append("LLM_PROMPT_SHA256")

    if problems:
        return None, problems
    return (
        GatewayConfig(
            api_key=settings.llm_api_key,
            url=settings.llm_base_url.rstrip("/") + "/chat/completions",
            model=model,
            max_tokens=settings.llm_max_tokens,
            max_tokens_param=settings.llm_max_tokens_param,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            prices=Prices(
                input=settings.llm_price_input_eur,
                cached_input=cached,
                output=settings.llm_price_output_eur,
            ),
            budget_month_micros=int(settings.llm_budget_month_eur * 1_000_000),
            budget_day_micros=int(settings.llm_budget_day_eur * 1_000_000),
            calls_per_minute=settings.llm_calls_per_minute,
            prompt_sha256=pinned,
        ),
        [],
    )


# --- llm_usage -------------------------------------------------------------------


@dataclass(frozen=True)
class UsageRecord:
    """Eine Zeile in ``llm_usage``. Nur Zahlen und kurze Codes, kein Inhalt."""

    occurred_at: datetime
    model: str
    status: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    cost_micros: int = 0
    latency_ms: int | None = None


class Ledger(Protocol):
    async def spent(self, since_month: datetime, since_day: datetime) -> tuple[int, int]:
        """Summe von ``cost_micros`` ab Monats- und ab Tagesanfang."""

    async def record(self, entry: UsageRecord) -> None: ...


class DbLedger:
    """``llm_usage`` in PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def spent(self, since_month: datetime, since_day: datetime) -> tuple[int, int]:
        statement = select(
            func.coalesce(func.sum(LlmUsage.cost_micros), 0),
            func.coalesce(
                func.sum(LlmUsage.cost_micros).filter(LlmUsage.occurred_at >= since_day), 0
            ),
        ).where(LlmUsage.occurred_at >= since_month)
        async with self._factory() as session:
            month, day = (await session.execute(statement)).one()
        return int(month), int(day)

    async def record(self, entry: UsageRecord) -> None:
        async with self._factory() as session:
            session.add(LlmUsage(**asdict(entry)))
            await session.commit()


# --- Antworten -------------------------------------------------------------------

# (HTTP-Status, type, code, Text). Neutral und kurz: Cowrie schreibt den Text
# in sein Log, und wer den Sensor übernimmt, liest mit.
_ERRORS: dict[str, tuple[int, str, str, str]] = {
    "unauthorized": (401, "authentication_error", "invalid_token", "nicht berechtigt"),
    "unavailable": (503, "server_error", "unavailable", "Dienst nicht verfügbar"),
    "too_large": (413, "invalid_request_error", "request_too_large", "Anfrage zu groß"),
    "invalid": (400, "invalid_request_error", "invalid_request", "Anfrage ungültig"),
    "budget_exceeded": (429, "rate_limit_error", "budget_exceeded", "Grenze erreicht"),
    "rate_limited": (429, "rate_limit_error", "rate_limited", "Grenze erreicht"),
    "timeout": (504, "server_error", "upstream_timeout", "Zeitüberschreitung"),
    "upstream_error": (502, "server_error", "upstream_error", "Anbieter nicht verfügbar"),
    "internal": (500, "server_error", "internal_error", "interner Fehler"),
}


def error_response(kind: str, headers: dict[str, str] | None = None) -> JSONResponse:
    status_code, error_type, code, message = _ERRORS[kind]
    body = {"error": {"message": message, "type": error_type, "param": None, "code": code}}
    return JSONResponse(body, status_code=status_code, headers=headers)


def completion_response(content: str, finish_reason: str, model: str, created: datetime) -> dict:
    """Die Antwort im OpenAI-Format, vom Gateway selbst gebaut.

    Vom Anbieter kommen nur ``content`` und ``finish_reason``. Cowrie liest
    ``choices[0].message.content``.
    """
    return {
        "id": f"chatcmpl-{secrets.token_hex(12)}",
        "object": "chat.completion",
        "created": int(created.timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }


# --- Anbieter --------------------------------------------------------------------


class _TooLarge(Exception):
    pass


@dataclass
class Outcome:
    """Was beim Anbieter herauskam."""

    status: str
    latency_ms: int
    usage: Usage = field(default_factory=Usage)
    cost_micros: int = 0
    estimated: bool = False
    upstream_status: int | None = None
    content: str = ""
    finish_reason: str = "stop"


def _choice(payload: Any) -> tuple[str, str] | None:
    """``content`` und ``finish_reason`` aus der ersten Wahl, sonst ``None``."""
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if content is None:
        # Etwa bei einer Weigerung des Modells. Cowrie gibt dann nichts aus.
        content = ""
    if not isinstance(content, str):
        return None
    finish = choices[0].get("finish_reason")
    return content, finish if finish in FINISH_REASONS else "stop"


# --- Gateway ---------------------------------------------------------------------


class Gateway:
    """Zustand und Ablauf des Gateways, einmal je Prozess."""

    def __init__(
        self,
        *,
        token: str,
        config: GatewayConfig | None,
        enabled: bool,
        model_hint: str,
        ledger: Ledger,
        clock: Callable[[], datetime],
        monotonic: Callable[[], float] = time.monotonic,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self.config = config
        self.enabled = enabled and config is not None
        self._model = config.model if config else model_hint
        self.ledger = ledger
        self._clock = clock
        self._monotonic = monotonic
        self.budget = Budget(config.budget_month_micros, config.budget_day_micros) if config else None
        self.window = CallWindow(config.calls_per_minute) if config else None
        self._client: httpx2.AsyncClient | None = None
        if self.enabled:
            assert config is not None
            self._client = httpx2.AsyncClient(
                timeout=httpx2.Timeout(
                    config.timeout_seconds,
                    connect=min(CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
                ),
                # Kein Proxy aus der Umgebung, keine .netrc, keine Weiterleitung.
                trust_env=False,
                follow_redirects=False,
                transport=transport,
            )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        ledger: Ledger,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic: Callable[[], float] = time.monotonic,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> Gateway:
        """Baut das Gateway. Wirft nie: Ingest und Statistik hängen nicht daran."""
        token = settings.llm_gateway_token.get_secret_value()
        if secret_problem(token):
            token = ""
        config, problems = build_config(settings)
        try:
            gateway = cls(
                token=token,
                config=config,
                enabled=settings.llm_gateway_enabled,
                model_hint=settings.llm_model.strip()[:MAX_MODEL_CHARS],
                ledger=ledger,
                clock=clock,
                monotonic=monotonic,
                transport=transport,
            )
        except Exception as exc:  # noqa: BLE001 - die API muss trotzdem starten
            logger.error("llm-gateway nicht gestartet", extra={"error": type(exc).__name__})
            return cls(
                token=token,
                config=None,
                enabled=False,
                model_hint="",
                ledger=ledger,
                clock=clock,
                monotonic=monotonic,
            )

        if gateway.enabled:
            assert config is not None
            logger.info(
                "llm-gateway bereit",
                extra={
                    "model": config.model,
                    "max_tokens": config.max_tokens,
                    "max_tokens_param": config.max_tokens_param,
                    "temperature": config.temperature,
                    "timeout_s": config.timeout_seconds,
                    "calls_per_minute": config.calls_per_minute,
                    "budget_monat_micros": config.budget_month_micros,
                    "budget_tag_micros": config.budget_day_micros,
                    "prompt_gepinnt": bool(config.prompt_sha256),
                },
            )
        else:
            logger.warning(
                "llm-gateway aus",
                extra={"abgeschaltet": not settings.llm_gateway_enabled, "fehlt": problems},
            )
        return gateway

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    # --- Ablauf ------------------------------------------------------------------

    async def handle(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None
    ) -> JSONResponse:
        started_at = self._clock()

        if not self._token:
            logger.warning("llm-gateway ohne token")
            return error_response("unavailable")
        if not token_matches(credentials, self._token):
            logger.warning("llm-gateway abgelehnt", extra=rejection_fields(credentials, self._token))
            return error_response("unauthorized")

        if not self.enabled:
            await self._finish(UsageRecord(started_at, self._model, "disabled"), http=503)
            return error_response("unavailable")
        config, budget, window = self.config, self.budget, self.window
        assert config is not None and budget is not None and window is not None

        try:
            checked = parse_request(await _read_body(request), config.prompt_sha256)
        except RequestRejected as exc:
            too_large = exc.reason == "rumpf_zu_gross"
            extra: dict[str, Any] = {"grund": exc.reason}
            if exc.persona_sha256:
                extra["prompt_sha256"] = exc.persona_sha256
            await self._finish(
                UsageRecord(started_at, config.model, "rejected"),
                http=413 if too_large else 400,
                extra=extra,
            )
            return error_response("too_large" if too_large else "invalid")
        # Nur der Hash des Persona-Teils, nie Inhalt. Steht in jeder Logzeile:
        # So zeigt sich, dass Exec und interaktiv denselben Prompt schicken, und
        # in 7.3 lässt sich genau der Wert pinnen, der wirklich ankommt.
        prompt = {"prompt_sha256": checked.persona_sha256}

        try:
            await budget.load(self.ledger.spent, started_at)
        except Exception as exc:  # noqa: BLE001 - ohne Budgetstand kein Aufruf
            logger.error("llm-budget nicht lesbar", extra={"error": type(exc).__name__})
            return error_response("unavailable")
        if budget.exceeded(self._clock()):
            await self._finish(
                UsageRecord(started_at, config.model, "budget_exceeded"), http=429, extra=prompt
            )
            return error_response("budget_exceeded")
        wait = window.acquire(self._monotonic())
        if wait > 0:
            await self._finish(
                UsageRecord(started_at, config.model, "rate_limited"), http=429, extra=prompt
            )
            return error_response("rate_limited", headers={"Retry-After": str(max(1, round(wait)))})

        outcome = await self._forward(config, checked)
        # Sofort zählen, noch vor dem Schreiben in die Datenbank: Die nächste
        # Anfrage soll die Kosten schon sehen.
        budget.add(outcome.cost_micros, started_at, self._clock())
        record = UsageRecord(
            occurred_at=started_at,
            model=config.model,
            status=outcome.status,
            prompt_tokens=outcome.usage.prompt_tokens,
            completion_tokens=outcome.usage.completion_tokens,
            total_tokens=outcome.usage.total_tokens,
            cached_tokens=outcome.usage.cached_tokens,
            cost_micros=outcome.cost_micros,
            latency_ms=outcome.latency_ms,
        )
        http = {"ok": 200, "timeout": 504}.get(outcome.status, 502)
        await self._finish(
            record,
            http=http,
            extra={
                **prompt,
                "upstream_status": outcome.upstream_status,
                "geschaetzt": outcome.estimated,
            },
        )
        if outcome.status == "ok":
            return JSONResponse(
                completion_response(outcome.content, outcome.finish_reason, config.model, started_at)
            )
        return error_response(outcome.status)

    async def _forward(self, config: GatewayConfig, checked: CheckedRequest) -> Outcome:
        """Ein Aufruf beim Anbieter, ohne Wiederholung."""
        assert self._client is not None
        payload = {
            "model": config.model,
            # Unverändert, damit der Anbieter den gleichbleibenden Anfang
            # zwischenspeichern kann (E-015).
            "messages": checked.messages,
            config.max_tokens_param: config.max_tokens,
            "temperature": config.temperature,
        }
        headers = {
            "Authorization": f"Bearer {config.api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        estimate = estimate_micros(checked.chars, config.max_tokens, config.prices)
        started = self._monotonic()

        def elapsed() -> int:
            return int((self._monotonic() - started) * 1000)

        try:
            async with asyncio.timeout(config.timeout_seconds):
                async with self._client.stream(
                    "POST", config.url, content=json.dumps(payload).encode("utf-8"), headers=headers
                ) as response:
                    upstream_status = response.status_code
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_UPSTREAM_BYTES:
                            raise _TooLarge
        except (TimeoutError, httpx2.TimeoutException):
            # Der Anbieter rechnet ab, auch wenn wir nicht mehr warten.
            return Outcome("timeout", elapsed(), cost_micros=estimate, estimated=True)
        except (_TooLarge, httpx2.HTTPError, OSError):
            return Outcome("upstream_error", elapsed())

        latency = elapsed()
        if upstream_status != 200:
            return Outcome("upstream_error", latency, upstream_status=upstream_status)
        try:
            parsed = json.loads(body)
        except (ValueError, RecursionError):
            return Outcome("upstream_error", latency, upstream_status=upstream_status)

        usage = parse_usage(parsed)
        if usage is None:
            cost, estimated, usage = estimate, True, Usage()
        else:
            cost, estimated = cost_micros(usage, config.prices), False
        choice = _choice(parsed)
        if choice is None:
            return Outcome(
                "upstream_error", latency, usage, cost, estimated, upstream_status=upstream_status
            )
        content, finish_reason = choice
        return Outcome(
            "ok", latency, usage, cost, estimated, upstream_status, content, finish_reason
        )

    async def _finish(
        self, record: UsageRecord, *, http: int, extra: dict[str, Any] | None = None
    ) -> None:
        """Schreibt die Zeile und eine Logzeile, beides ohne Inhalt."""
        try:
            await self.ledger.record(record)
        except Exception as exc:  # noqa: BLE001 - die Antwort geht trotzdem raus
            logger.error("llm_usage nicht geschrieben", extra={"error": type(exc).__name__})
        logger.info(
            "llm",
            extra={
                "status": record.status,
                "http": http,
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "cached_tokens": record.cached_tokens,
                "cost_micros": record.cost_micros,
                "latency_ms": record.latency_ms,
                **(extra or {}),
            },
        )


async def _read_body(request: Request) -> bytes:
    """Liest den Rumpf, höchstens ``MAX_BODY_BYTES``."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise RequestRejected("rumpf_zu_gross")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise RequestRejected("rumpf_zu_gross")
    return bytes(body)


def gateway_of(request: Request) -> Gateway:
    return request.app.state.llm_gateway


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    gateway: Gateway = Depends(gateway_of),
) -> JSONResponse:
    try:
        return await gateway.handle(request, credentials)
    except Exception as exc:  # noqa: BLE001 - kein Traceback, er könnte Inhalt tragen
        logger.error("llm-gateway fehler", extra={"error": type(exc).__name__})
        return error_response("internal")
