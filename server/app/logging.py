"""Strukturierte Logs als JSON, eine Zeile je Ereignis.

Zwei Regeln stecken hier drin:

- Keine Klartext-IPs. Uvicorns Access-Log schreibt die Adresse jedes Clients
  mit, deshalb läuft die API mit ``--no-access-log`` und loggt stattdessen
  selbst (siehe ``app.main``): Methode, Pfad, Status, Dauer, sonst nichts.
- Keine Secrets. Werte stehen nur als ``SecretStr`` in den Einstellungen und
  werden nie in ein Log-Feld geschrieben.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Felder, die ein LogRecord immer mitbringt. Alles andere, was jemand per
# ``extra=`` anhängt, landet zusätzlich im JSON.
_STANDARD_FIELDS = frozenset(
    """
    args asctime created exc_info exc_text filename funcName levelname levelno
    lineno module msecs message msg name pathname process processName
    relativeCreated stack_info taskName thread threadName
    """.split()
)


class JsonFormatter(logging.Formatter):
    """Formatiert einen LogRecord als eine Zeile JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Richtet das Logging für API und Worker ein."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn bringt eigene Handler mit. Ohne das hier stünde jede Zeile
    # doppelt im Log, einmal als Text und einmal als JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
