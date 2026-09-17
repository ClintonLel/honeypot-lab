"""Anreicherung der Quell-IP mit Land und Netzbetreiber.

Reihenfolge laut E-009: erst anreichern, dann hashen, dann den Klartext
verwerfen. Aus einem Hash ließe sich das Land nicht mehr bestimmen.

Die Datenbank ist IPinfo Lite (CC BY-SA 4.0). Der Worker lädt sie täglich
(Schritt 4.3). Fehlt die Datei, läuft der Ingest weiter und speichert die
Sitzung ohne Land: Ein fehlender Download darf keine Ereignisse kosten.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("lab.enrichment")


@dataclass(frozen=True)
class Origin:
    """Was wir über die Herkunft speichern dürfen."""

    country: str | None = None
    asn: str | None = None
    as_name: str | None = None


EMPTY = Origin()


class Enricher:
    """Liest die MMDB und beantwortet Anfragen. Öffnet die Datei verzögert."""

    def __init__(self, path: str | Path | None) -> None:
        self._path = Path(path) if path else None
        self._reader: Any = None
        self._mtime: float | None = None
        self._lock = threading.Lock()
        self._warned = False

    def _ensure_reader(self) -> Any:
        if self._path is None:
            return None
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            if not self._warned:
                logger.warning("ipinfo-datenbank fehlt", extra={"path": str(self._path)})
                self._warned = True
            return None

        with self._lock:
            # Der Worker ersetzt die Datei atomar. Nach einem Tausch neu öffnen.
            if self._reader is None or mtime != self._mtime:
                import maxminddb

                if self._reader is not None:
                    self._reader.close()
                self._reader = maxminddb.open_database(str(self._path))
                self._mtime = mtime
                self._warned = False
                logger.info("ipinfo-datenbank geladen", extra={"path": str(self._path)})
            return self._reader

    def lookup(self, address: str | None) -> Origin:
        if not address:
            return EMPTY
        reader = self._ensure_reader()
        if reader is None:
            return EMPTY
        try:
            record = reader.get(address)
        except (ValueError, OSError) as exc:
            logger.warning("anreicherung fehlgeschlagen", extra={"error": type(exc).__name__})
            return EMPTY
        if not isinstance(record, dict):
            return EMPTY
        return Origin(
            country=_short(record.get("country_code"), 2),
            asn=_short(record.get("asn"), 16),
            as_name=_short(record.get("as_name"), 128),
        )

    def close(self) -> None:
        with self._lock:
            if self._reader is not None:
                self._reader.close()
                self._reader = None


def _short(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:limit]
