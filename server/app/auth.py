"""Bearer-Token des Sensors prüfen, für ``/ingest`` und das LLM-Gateway.

Verglichen wird in konstanter Zeit und auf Bytes: ``hmac.compare_digest``
wirft bei Strings mit Nicht-ASCII-Zeichen einen ``TypeError``, und den Header
schreibt der Absender. Geloggt wird nur die Form des Headers, nie der Wert.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def token_matches(credentials: HTTPAuthorizationCredentials | None, expected: str) -> bool:
    """True, wenn das mitgeschickte Token dem erwarteten entspricht.

    Ein leeres erwartetes Token passt nie, sonst käme man ohne Token durch.
    """
    if not expected:
        return False
    given = credentials.credentials if credentials else ""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def rejection_fields(
    credentials: HTTPAuthorizationCredentials | None, expected: str
) -> dict[str, Any]:
    """Felder für die Logzeile einer Ablehnung: Schema, Länge und ob ein
    Platzhalter durchgereicht wurde. Nie der Wert selbst."""
    given = credentials.credentials if credentials else ""
    return {
        "scheme": credentials.scheme if credentials else None,
        "laenge": len(given),
        "erwartete_laenge": len(expected),
        "sieht_aus_wie_platzhalter": given.startswith("${"),
    }
