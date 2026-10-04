"""Attrappen für die Tests des LLM-Gateways: Anbieter, Ledger, Einstellungen.

Kein Test ruft einen echten Anbieter. Die Attrappe hängt über
``httpx2.MockTransport`` direkt im Client des Gateways; eine Verbindung ins
Netz entsteht nie.

Die Attrappe spielt Geminis OpenAI-kompatiblen Endpunkt (E-045): Antworten
mit Gemini-Feldern, Fehler als Liste ``[{"error": …}]``, und sie lehnt wie
Gemini Anfragen ohne user-Nachricht und Nachrichten mit leerem Text ab, auf
Wunsch auch zwei Nachrichten derselben Rolle in Folge (``strict_turns``).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx2

from app.config import Settings
from app.llm_gateway import UsageRecord

# Nur für Tests, ohne Ähnlichkeit zu echten Schlüsseln.
API_KEY = "testkey-" + "k" * 56
GATEWAY_TOKEN = "g" * 64
TEST_SECRET = "t" * 64

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
MODEL = "gemini-3.1-flash-lite"
ANSWER = "Linux test-host 6.12.107+deb13-amd64 #1 SMP x86_64 GNU/Linux"


def llm_settings(**overrides: Any) -> Settings:
    """Ein vollständig konfiguriertes, eingeschaltetes Gateway."""
    values: dict[str, Any] = {
        "environment": "test",
        "postgres_password": TEST_SECRET,
        "ip_hmac_key": TEST_SECRET,
        "ingest_token": TEST_SECRET,
        "llm_gateway_enabled": True,
        "llm_api_key": API_KEY,
        "llm_gateway_token": GATEWAY_TOKEN,
        "llm_model": MODEL,
        "llm_max_tokens": 2048,
        "llm_temperature": 1.0,
        "llm_reasoning_effort": "minimal",
        "llm_merge_turns": False,
        "llm_timeout_seconds": 5,
        "llm_budget_month_usd": "20",
        "llm_budget_day_usd": "2",
        "llm_calls_per_minute": 60,
        "llm_prompt_sha256": "",
    }
    values.update(overrides)
    return Settings(**values)


def auth(token: str = GATEWAY_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class MemoryLedger:
    """``llm_usage`` im Speicher. ``month``/``day`` sind Kosten von früher."""

    def __init__(self, month: int = 0, day: int = 0) -> None:
        self.rows: list[UsageRecord] = []
        self.month = month
        self.day = day
        self.fail_spent = False
        self.fail_record = False

    async def spent(self, since_month: datetime, since_day: datetime) -> tuple[int, int]:
        if self.fail_spent:
            raise ConnectionError("datenbank weg")
        month = self.month + sum(r.cost_micros for r in self.rows if r.occurred_at >= since_month)
        day = self.day + sum(r.cost_micros for r in self.rows if r.occurred_at >= since_day)
        return month, day

    async def record(self, entry: UsageRecord) -> None:
        if self.fail_record:
            raise ConnectionError("datenbank weg")
        self.rows.append(entry)

    @property
    def statuses(self) -> list[str]:
        return [r.status for r in self.rows]


def completion(
    content: Any = ANSWER,
    *,
    prompt: int = 8000,
    cached: int = 7424,
    completion_tokens: int = 20,
    thoughts: int = 0,
    thoughts_in: str = "total",
    finish_reason: str = "stop",
    usage: bool = True,
) -> dict[str, Any]:
    """Eine Antwort, wie Geminis kompatibler Endpunkt sie schickt.

    ``thoughts_in`` ist eine der beiden Lesarten für Denk-Tokens (E-045):
    ``"total"``: nicht in ``completion_tokens``, nur in ``total_tokens``;
    ``"details"``: wie OpenAI in ``completion_tokens`` und dazu einzeln in
    ``completion_tokens_details.reasoning_tokens``.
    """
    body: dict[str, Any] = {
        "id": "anbieter-interne-id",
        "object": "chat.completion",
        "created": 1_791_000_000,
        "model": "gemini-3.1-flash-lite-intern",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        if thoughts_in == "details":
            body["usage"] = {
                "prompt_tokens": prompt,
                "completion_tokens": completion_tokens + thoughts,
                "total_tokens": prompt + completion_tokens + thoughts,
                "prompt_tokens_details": {"cached_tokens": cached},
                "completion_tokens_details": {"reasoning_tokens": thoughts},
            }
        else:
            body["usage"] = {
                "prompt_tokens": prompt,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt + completion_tokens + thoughts,
                "prompt_tokens_details": {"cached_tokens": cached},
            }
    return body


def gemini_error(status: int, message: str = "fehler") -> list[dict[str, Any]]:
    """Ein Fehlerrumpf, wie Geminis kompatibler Endpunkt ihn schickt: als Liste."""
    names = {400: "INVALID_ARGUMENT", 402: "PAYMENT_REQUIRED", 429: "RESOURCE_EXHAUSTED", 500: "INTERNAL"}
    return [{"error": {"code": status, "message": message, "status": names.get(status, "UNKNOWN")}}]


def gemini_problem(payload: dict[str, Any], strict_turns: bool) -> str | None:
    """Was Gemini an der Anfrage ablehnen würde, sonst ``None``."""
    turns = [m for m in payload.get("messages", []) if m.get("role") != "system"]
    if not turns:
        return "contents is not specified"
    if any(not str(m.get("content", "")).strip() for m in payload.get("messages", [])):
        return "Unable to submit request because it has an empty text parameter"
    if strict_turns and any(a["role"] == b["role"] for a, b in zip(turns, turns[1:])):
        return "Please ensure that multiturn requests alternate between user and model"
    return None


Reply = Callable[[httpx2.Request], httpx2.Response]


class Upstream:
    """Der Anbieter als Attrappe. Merkt sich jede Anfrage.

    ``validate``: Anfragen, die Gemini ablehnt, bekommen 400 statt ``reply``.
    """

    def __init__(
        self,
        reply: Reply | None = None,
        delay: float = 0.0,
        *,
        validate: bool = True,
        strict_turns: bool = False,
    ) -> None:
        self.reply: Reply = reply or (lambda request: httpx2.Response(200, json=completion()))
        self.delay = delay
        self.validate = validate
        self.strict_turns = strict_turns
        self.requests: list[httpx2.Request] = []
        self.in_flight = 0
        self.peak = 0

    @property
    def calls(self) -> int:
        return len(self.requests)

    def payload(self, index: int = -1) -> dict[str, Any]:
        return json.loads(self.requests[index].content)

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.validate:
                problem = gemini_problem(json.loads(request.content), self.strict_turns)
                if problem:
                    return httpx2.Response(400, json=gemini_error(400, problem))
            return self.reply(request)
        finally:
            self.in_flight -= 1

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)
