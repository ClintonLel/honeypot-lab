"""Kosten, Budget und Minutengrenze des LLM-Gateways (Schritt 7.2, E-043, E-045).

Kosten und Budgets in US-Dollar, wie Googles Preise (E-045). ``cost_micros``
heißt Millionstel Dollar.

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
    """US-Dollar je eine Million Tokens. Das ist zugleich Mikro-Dollar je Token.

    ``output`` gilt auch für Denk-Tokens (E-045).
    """

    input: Decimal
    cached_input: Decimal
    output: Decimal


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    # Abgerechnete Ausgabe, Denk-Tokens eingeschlossen.
    completion_tokens: int = 0
    total_tokens: int = 0
    # Teil von prompt_tokens aus dem Zwischenspeicher des Anbieters.
    cached_tokens: int = 0
    # Teil von completion_tokens, den das Modell zum Denken brauchte.
    reasoning_tokens: int = 0


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return min(value, INT4_MAX)


def parse_usage(payload: Any) -> Usage | None:
    """Liest ``usage`` aus der Antwort des Anbieters. ``None``, wenn es fehlt.

    Wie Geminis kompatibler Endpunkt Denk-Tokens meldet, ist nicht
    dokumentiert (E-045). Zwei Lesarten kommen vor: Sie stecken wie bei
    OpenAI in ``completion_tokens`` (und ``total_tokens`` ist Eingabe plus
    Ausgabe), oder sie fehlen dort und stecken nur in ``total_tokens``.
    Abgerechnet wird deshalb ``max(completion_tokens, total_tokens -
    prompt_tokens)``; ohne ``total_tokens`` ``completion_tokens`` plus
    ``completion_tokens_details.reasoning_tokens``. Das bucht im Zweifel
    mehr, nie weniger. Zwischengespeicherte Tokens stehen in
    ``prompt_tokens_details.cached_tokens`` und sind in ``prompt_tokens``
    enthalten.
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
    reasoning = _detail(usage, "completion_tokens_details", "reasoning_tokens")
    total = _count(usage.get("total_tokens"))
    if total is not None:
        output = max(completion, total - prompt)
    else:
        output = completion + (reasoning or 0)
    output = min(output, INT4_MAX)
    thoughts = reasoning if reasoning is not None else output - completion
    cached = _detail(usage, "prompt_tokens_details", "cached_tokens")
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=output,
        total_tokens=min(max(total or 0, prompt + output), INT4_MAX),
        cached_tokens=min(cached or 0, prompt),
        reasoning_tokens=min(thoughts, output),
    )


def _detail(usage: dict[str, Any], group: str, key: str) -> int | None:
    details = usage.get(group)
    return _count(details.get(key)) if isinstance(details, dict) else None


def _micros(amount: Decimal) -> int:
    # Aufrunden: Lieber einen Mikro-Dollar zu viel zählen als zu wenig.
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def cost_micros(usage: Usage, prices: Prices) -> int:
    """Kosten eines Aufrufs in Millionstel Dollar. Denk-Tokens stecken in
    ``completion_tokens`` und kosten wie Ausgabe."""
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
    volle Ausgabe; die Ausgabegrenze schließt Denk-Tokens ein.
    """
    input_tokens = -(-chars // CHARS_PER_TOKEN_ESTIMATE)
    return _micros(input_tokens * prices.input + max_tokens * prices.output)


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc)


def month_start(now: datetime) -> datetime:
    return _utc(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def day_start(now: datetime) -> datetime:
    return _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)


# Liest die Summe der Kosten ab Monats- und ab Tagesanfang, in Mikro-Dollar.
SpentReader = Callable[[datetime, datetime], Awaitable[tuple[int, int]]]


class Budget:
    """Ausgaben des laufenden Monats und Tages (UTC) in Mikro-Dollar."""

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
