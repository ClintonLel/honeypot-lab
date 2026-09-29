"""GET /stream: Live-Ereignisse als Server-Sent Events (Schritt 5.1).

Der Ingest meldet jedes neu gespeicherte Ereignis nach dem Commit an den
Verteiler. Jeder verbundene Client hat eine eigene, begrenzte Warteschlange:
Wer nicht mitkommt, verliert die ältesten Meldungen, bremst aber weder den
Ingest noch andere Clients.

Der Verteiler lebt im Speicher der API. Das trägt, solange die API als ein
Prozess läuft (E-029). Mit mehreren Prozessen müsste PostgreSQL LISTEN/NOTIFY
an seine Stelle treten.

Eine Meldung enthält nur Zeitpunkt, Variante, Land, Ereignistyp und bei
Befehlen eine Vorschau von höchstens 80 Zeichen samt ATT&CK-Techniken. Die Vorschau ist schon beim
Ingest entschärft worden, die Adresse des Angreifers steht darin nie. Keine
Sitzungs-ID, kein Hash: Aus dem Stream lässt sich niemand wiedererkennen.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.attack import classify
from app.defang import shorten
from app.events import NormalizedEvent
from app.ratelimit import RateLimiter, client_key

router = APIRouter()

# Nur was auf der Seite etwas bedeutet. Schlüsseltausch, Terminalgröße und
# Ähnliches bleiben draußen.
STREAM_EVENTS = {
    "cowrie.session.connect": "connect",
    "cowrie.login.success": "login",
    "cowrie.login.failed": "login_failed",
    "cowrie.command.input": "command",
    "cowrie.session.file_download": "download",
    "cowrie.session.closed": "closed",
}

PREVIEW_LENGTH = 80
QUEUE_SIZE = 100
MAX_SUBSCRIBERS = 200
HEARTBEAT_SECONDS = 15.0
RETRY_MS = 5000


def stream_message(event: NormalizedEvent, country: str | None) -> dict[str, Any] | None:
    """Macht aus einem gespeicherten Ereignis eine Meldung für den Stream."""
    kind = STREAM_EVENTS.get(event.eventid)
    if kind is None:
        return None
    message: dict[str, Any] = {
        "ts": event.occurred_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "variant": event.variant,
        "country": country,
        "event": kind,
    }
    if kind == "command":
        # fields["input"] ist schon gekürzt, ohne Adresse des Angreifers und
        # entschärft (app.events). Hier nur noch auf die Vorschaulänge.
        text = event.fields.get("input") or ""
        message["command"] = shorten(text, PREVIEW_LENGTH)
        # Auf dem ganzen Befehl, nicht auf der Vorschau. Dasselbe Ergebnis,
        # das der Ingest in commands.techniques schreibt (E-037).
        message["techniques"] = classify(text)
    return message


class Broadcaster:
    """Verteilt Meldungen an alle verbundenen Clients."""

    def __init__(self, queue_size: int = QUEUE_SIZE, max_subscribers: int = MAX_SUBSCRIBERS) -> None:
        self.queue_size = queue_size
        self.max_subscribers = max_subscribers
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]] | None:
        if len(self._subscribers) >= self.max_subscribers:
            return None
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, message: dict[str, Any]) -> None:
        for queue in self._subscribers:
            if queue.full():
                # Der Client kommt nicht mit. Lieber die älteste Meldung
                # verwerfen als alle anderen warten lassen.
                queue.get_nowait()
            queue.put_nowait(message)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


def sse_data(message: dict[str, Any]) -> str:
    # json.dumps erzeugt keine Zeilenumbrüche, eine Meldung ist eine Zeile.
    return f"data: {json.dumps(message, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def sse_events(
    queue: asyncio.Queue[dict[str, Any]],
    is_disconnected: Callable[[], Awaitable[bool]],
    heartbeat: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Die eigentliche Ereignisfolge, ohne HTTP drumherum, damit testbar."""
    # Nach einem Abbruch verbindet der Browser nach 5 Sekunden neu.
    yield f"retry: {RETRY_MS}\n\n"
    while not await is_disconnected():
        try:
            message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
        except TimeoutError:
            # Kommentarzeile als Lebenszeichen, damit Proxys nicht schließen.
            yield ": ping\n\n"
            continue
        yield sse_data(message)


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    limiter: RateLimiter = request.app.state.limiter
    broadcaster: Broadcaster = request.app.state.broadcaster
    key = client_key(request)

    if not limiter.acquire_stream(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="zu viele offene Streams",
            headers={"Retry-After": "30"},
        )
    queue = broadcaster.subscribe()
    if queue is None:
        limiter.release_stream(key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stream ausgelastet",
            headers={"Retry-After": "30"},
        )

    async def body() -> AsyncIterator[str]:
        try:
            async for chunk in sse_events(queue, request.is_disconnected):
                yield chunk
        finally:
            broadcaster.unsubscribe(queue)
            limiter.release_stream(key)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def publish_stored(request: Request, stored: list[tuple[NormalizedEvent, str | None]]) -> int:
    """Wird vom Ingest nach dem Commit aufgerufen. Gibt die Zahl der Meldungen zurück."""
    broadcaster: Broadcaster | None = getattr(request.app.state, "broadcaster", None)
    if broadcaster is None or broadcaster.subscriber_count == 0:
        return 0
    sent = 0
    for event, country in stored:
        message = stream_message(event, country)
        if message is not None:
            broadcaster.publish(message)
            sent += 1
    return sent
