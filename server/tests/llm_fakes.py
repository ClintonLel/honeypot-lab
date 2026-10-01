"""Attrappen für die Tests des LLM-Gateways: Anbieter, Ledger, Einstellungen.

Kein Test ruft einen echten Anbieter. Die Attrappe hängt über
``httpx2.MockTransport`` direkt im Client des Gateways; eine Verbindung ins
Netz entsteht nie.
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
BASE_URL = "https://llm.example.test/v1"
MODEL = "test-model-mini"
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
        "llm_base_url": BASE_URL,
        "llm_model": MODEL,
        "llm_max_tokens": 2048,
        "llm_max_tokens_param": "max_completion_tokens",
        "llm_temperature": 0.0,
        "llm_timeout_seconds": 5,
        "llm_price_input_eur": "0.40",
        "llm_price_cached_input_eur": "0.10",
        "llm_price_output_eur": "1.60",
        "llm_budget_month_eur": "20",
        "llm_budget_day_eur": "2",
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
    finish_reason: str = "stop",
    usage: bool = True,
) -> dict[str, Any]:
    """Eine Antwort, wie OpenAI sie schickt, mit Feldern, die das Gateway nicht weitergibt."""
    body: dict[str, Any] = {
        "id": "chatcmpl-anbieter-intern",
        "object": "chat.completion",
        "created": 1_791_000_000,
        "model": "anbieter-modell-2026-09-01",
        "system_fingerprint": "fp_anbieter",
        "service_tier": "default",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "refusal": None, "annotations": []},
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        body["usage"] = {
            "prompt_tokens": prompt,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": cached, "audio_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0},
        }
    return body


Reply = Callable[[httpx2.Request], httpx2.Response]


class Upstream:
    """Der Anbieter als Attrappe. Merkt sich jede Anfrage."""

    def __init__(self, reply: Reply | None = None, delay: float = 0.0) -> None:
        self.reply: Reply = reply or (lambda request: httpx2.Response(200, json=completion()))
        self.delay = delay
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
            return self.reply(request)
        finally:
            self.in_flight -= 1

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)
