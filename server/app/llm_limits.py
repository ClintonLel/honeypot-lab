"""Kosten, Budget und Minutengrenze des LLM-Gateways (Schritt 7.2, E-043).

Budget und Minutengrenze leben im Speicher dieses Prozesses, wie Stream und
Rate-Limit (E-029). Uvicorn läuft mit einem Prozess; mit mehreren hätte jeder
sein eigenes Budget, und die Grenzen vervielfachten sich.

Geprüft wird vor dem Aufruf beim Anbieter, ohne Kosten vorab zu reservieren.
Parallele Anfragen können das Budget deshalb überschreiten, aber höchstens um
die gerade laufenden. Weil das Zeitlimit unter 60 Sekunden liegt, laufen nie
mehr Anfragen gleichzeitig, als die Minutengrenze erlaubt.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_CEILING, Decimal
from typing import Any

# Obergrenze der Integer-Spalten in llm_usage.
INT4_MAX = 2**31 - 1

# Für die Schätzung: so viele Zeichen je Token. Englischer Text hat eher vier,
# drei schätzt eher zu hoch als zu niedrig.
CHARS_PER_TOKEN_ESTIMATE = 3


@dataclass(frozen=True)
class Prices:
    """Euro je eine Million Tokens. Das ist zugleich Mikro-Euro je Token."""

    input: Decimal
    cached_input: Decimal
    output: Decimal


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Teil von prompt_tokens aus dem Zwischenspeicher des Anbieters.
    cached_tokens: int = 0


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return min(value, INT4_MAX)


def parse_usage(payload: Any) -> Usage | None:
    """Liest ``usage`` aus der Antwort des Anbieters. ``None``, wenn es fehlt.

    Zwischengespeicherte Tokens stehen bei OpenAI in
    ``prompt_tokens_details.cached_tokens``, bei manchen anderen Anbietern in
    ``prompt_cache_hit_tokens``. In beiden Fällen sind sie in
    ``prompt_tokens`` enthalten.
    """
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = _count(usage.get("prompt_tokens"))
    completion = _count(usage.get("completion_tokens"))
    if prompt is None or completion is None:
        return None
    total = _count(usage.get("total_tokens"))
    if total is None:
        total = min(prompt + completion, INT4_MAX)
    cached = None
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = _count(details.get("cached_tokens"))
    if cached is None:
        cached = _count(usage.get("prompt_cache_hit_tokens"))
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cached_tokens=min(cached or 0, prompt),
    )


def _micros(amount: Decimal) -> int:
    # Aufrunden: Lieber einen Mikro-Euro zu viel zählen als zu wenig.
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def cost_micros(usage: Usage, prices: Prices) -> int:
    """Kosten eines Aufrufs in Millionstel Euro."""
    uncached = usage.prompt_tokens - usage.cached_tokens
    return _micros(
        uncached * prices.input
        + usage.cached_tokens * prices.cached_input
        + usage.completion_tokens * prices.output
    )


def estimate_micros(chars: int, max_tokens: int, prices: Prices) -> int:
    """Obere Schätzung, wenn der Anbieter keine Zahlen liefert.

    Bei einer Zeitüberschreitung rechnet der Anbieter trotzdem ab. Ohne
    Schätzung könnte ein langsamer Anbieter das Budget unbemerkt leeren.
    Angenommen werden: alle Eingabe-Tokens ohne Zwischenspeicher und die
    volle Ausgabe.
    """
    input_tokens = -(-chars // CHARS_PER_TOKEN_ESTIMATE)
    return _micros(input_tokens * prices.input + max_tokens * prices.output)


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc)


def month_start(now: datetime) -> datetime:
    return _utc(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def day_start(now: datetime) -> datetime:
    return _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)


# Liest die Summe der Kosten ab Monats- und ab Tagesanfang, in Mikro-Euro.
SpentReader = Callable[[datetime, datetime], Awaitable[tuple[int, int]]]


class Budget:
    """Ausgaben des laufenden Monats und Tages (UTC) in Mikro-Euro."""

    def __init__(self, month_micros: int, day_micros: int) -> None:
        self.month_limit = month_micros
        self.day_limit = day_micros
        self.spent_month = 0
        self.spent_day = 0
        self._today: date | None = None
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def loaded(self) -> bool:
        return self._loaded

    async def load(self, read: SpentReader, now: datetime) -> None:
        """Einmal nach dem Start: was diesen Monat und heute schon ausgegeben wurde.

        Unter Lock, damit gleichzeitige erste Anfragen nur einmal lesen.
        Scheitert das Lesen, bleibt das Budget ungeladen und der nächste
        Aufruf versucht es neu; bis dahin ruft das Gateway den Anbieter nicht.
        """
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            month, day = await read(month_start(now), day_start(now))
            self._today = _utc(now).date()
            self.spent_month = month
            self.spent_day = day
            self._loaded = True

    def _roll(self, now: datetime) -> date:
        """Neuer Tag: Tageszähler auf 0, neuer Monat: auch der Monatszähler."""
        today = _utc(now).date()
        if self._today is not None and today != self._today:
            if (today.year, today.month) != (self._today.year, self._today.month):
                self.spent_month = 0
            self.spent_day = 0
        self._today = today
        return today

    def exceeded(self, now: datetime) -> bool:
        self._roll(now)
        return self.spent_month >= self.month_limit or self.spent_day >= self.day_limit

    def add(self, micros: int, started_at: datetime, now: datetime) -> None:
        """Bucht Kosten auf den Monat und Tag, in dem die Anfrage begann.

        So zählt es auch ``llm_usage``: ``occurred_at`` ist der Beginn. Eine
        Anfrage über Mitternacht belastet den alten Tag, nicht den neuen.
        """
        today = self._roll(now)
        started = _utc(started_at).date()
        if (started.year, started.month) == (today.year, today.month):
            self.spent_month += micros
        if started == today:
            self.spent_day += micros


class CallWindow:
    """Gleitendes Fenster über alle Aufrufe beim Anbieter zusammen.

    Kein Token-Bucket wie ``app.ratelimit.RateLimiter``: Das Fenster lässt in
    keinen 60 Sekunden mehr als ``per_minute`` Aufrufe durch. Das begrenzt
    zugleich, wie viele gleichzeitig laufen können.
    """

    def __init__(self, per_minute: int, window_seconds: float = 60.0) -> None:
        self.per_minute = per_minute
        self.window = window_seconds
        self._calls: deque[float] = deque()

    def acquire(self, now: float) -> float:
        """0, wenn der Aufruf durchgeht (er zählt dann mit), sonst Sekunden bis
        zum nächsten freien Platz."""
        while self._calls and now - self._calls[0] >= self.window:
            self._calls.popleft()
        if len(self._calls) >= self.per_minute:
            return self.window - (now - self._calls[0])
        self._calls.append(now)
        return 0.0
