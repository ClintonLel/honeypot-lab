"""Rate-Limit pro Client für die öffentlichen Endpunkte (Schritt 5.1).

Die API ist nur über Caddy erreichbar (E-021), und Caddy setzt
``X-Forwarded-For`` selbst: Einen Wert, den ein Client mitschickt, übernimmt es
nicht. Der erste Eintrag ist deshalb die Adresse des Besuchers.

Auch die Adresse eines Besuchers ist eine IP. Sie wird sofort mit einem
Zufallswert je Prozess gehasht, und nur dieser Hash dient als Schlüssel. Die
Adresse selbst steht nie im Speicher des Limiters, im Log oder in der
Datenbank. Nach einem Neustart sind die Schlüssel neu, das ist gewollt.
"""

from __future__ import annotations

import secrets
import time
from collections import Counter, OrderedDict
from hashlib import sha256

from fastapi import HTTPException, Request, status

# Neu bei jedem Start. Ohne ihn ließe sich aus einem Schlüssel die Adresse
# durchprobieren, der IPv4-Raum ist klein (E-009).
_SALT = secrets.token_bytes(32)

STATS_PER_MINUTE = 60
STREAMS_PER_CLIENT = 3
MAX_KEYS = 10_000


def client_key(request: Request) -> str:
    """Kurzer Hash der Besucheradresse, nie die Adresse selbst."""
    forwarded = request.headers.get("x-forwarded-for", "")
    address = forwarded.split(",")[0].strip()
    if not address and request.client:
        address = request.client.host
    return sha256(_SALT + address.encode("utf-8")).hexdigest()[:32]


class RateLimiter:
    """Token-Bucket je Client plus Zähler für offene Streams."""

    def __init__(
        self,
        per_minute: int = STATS_PER_MINUTE,
        streams_per_client: int = STREAMS_PER_CLIENT,
        max_keys: int = MAX_KEYS,
    ) -> None:
        self.per_minute = per_minute
        self.streams_per_client = streams_per_client
        self.max_keys = max_keys
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._streams: Counter[str] = Counter()

    def allow(self, key: str, now: float | None = None) -> float:
        """Gibt 0 zurück, wenn die Anfrage durchgeht, sonst die Wartezeit in Sekunden."""
        now = time.monotonic() if now is None else now
        rate = self.per_minute / 60.0
        tokens, last = self._buckets.pop(key, (float(self.per_minute), now))
        tokens = min(float(self.per_minute), tokens + (now - last) * rate)
        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            wait = 0.0
        else:
            self._buckets[key] = (tokens, now)
            wait = (1.0 - tokens) / rate
        # Die ältesten Schlüssel fliegen raus, damit der Speicher begrenzt bleibt.
        while len(self._buckets) > self.max_keys:
            self._buckets.popitem(last=False)
        return wait

    def acquire_stream(self, key: str) -> bool:
        if self._streams[key] >= self.streams_per_client:
            return False
        self._streams[key] += 1
        return True

    def release_stream(self, key: str) -> None:
        self._streams[key] -= 1
        if self._streams[key] <= 0:
            del self._streams[key]

    @property
    def known_keys(self) -> list[str]:
        return list(self._buckets)


async def rate_limited(request: Request) -> None:
    """Abhängigkeit für die Statistik-Endpunkte."""
    limiter: RateLimiter = request.app.state.limiter
    wait = limiter.allow(client_key(request))
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="zu viele Anfragen",
            headers={"Retry-After": str(max(1, round(wait)))},
        )
