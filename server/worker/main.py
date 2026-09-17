"""Der Worker.

Gerüst mit Zeitplan-Schleife und sauberem Beenden. Die eigentlichen Jobs
kommen in Schritt 4.3: täglicher Download der IPinfo-Lite-Datenbank,
stündliche Aggregation in ``daily_stats`` und das Löschen von Roh-Events nach
90 Tagen. Der HMAC-Schlüssel rotiert nicht (E-022).

Der Worker hängt in ``lab_internal`` und ``lab_egress``: Er erreicht die
Datenbank und das Internet, aber niemand erreicht ihn.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress

from sqlalchemy import text

from app.config import get_settings
from app.db import create_engine
from app.logging import configure_logging

logger = logging.getLogger("lab.worker")

# Abstand zwischen zwei Durchläufen der Schleife.
TICK_SECONDS = 60


async def run_due_jobs() -> None:
    """Platzhalter. Ab Schritt 4.3 stehen hier die geplanten Jobs."""
    logger.debug("keine jobs eingeplant")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stopping.set)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("worker gestartet", extra={"tick_seconds": TICK_SECONDS})

        while not stopping.is_set():
            try:
                await run_due_jobs()
            except Exception as exc:  # noqa: BLE001 - ein Job darf den Worker nicht beenden
                logger.exception("job fehlgeschlagen", extra={"error": type(exc).__name__})
            with suppress(TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=TICK_SECONDS)
    finally:
        await engine.dispose()
        logger.info("worker beendet")


if __name__ == "__main__":
    asyncio.run(main())
