"""Freitexte entschärfen, bevor sie irgendwo angezeigt werden.

Regel aus AGENTS.md: „URLs und IPs in allen öffentlichen Ausgaben
entschärfen (hxxp://, [.])“. Angreifer-Befehle enthalten Adressen von
Systemen, die niemand aus Versehen anklicken oder ein Scanner automatisch
besuchen soll.

Entschärft wird beim Schreiben, nicht erst beim Anzeigen: In der Datenbank
steht damit von vornherein die harmlose Fassung, und kein späterer Endpunkt
kann die Entschärfung vergessen.
"""

from __future__ import annotations

import re

# Schemata, die ein Browser oder ein Werkzeug automatisch aufrufen könnte.
SCHEMES = {
    "http": "hxxp",
    "https": "hxxps",
    "ftp": "fxp",
    "tftp": "tfxp",
}

# URL bis zum ersten Leerzeichen oder Anführungszeichen.
URL = re.compile(
    r"\b(?P<scheme>https?|ftp|tftp)://(?P<rest>[^\s\"'<>\\|)]*)",
    re.IGNORECASE,
)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _defang_url(match: re.Match[str]) -> str:
    scheme = match.group("scheme").lower()
    rest = match.group("rest")
    # Nur der Namensteil wird entschärft, der Pfad bleibt lesbar: Aus
    # "beispiel.test/x.sh" wird "beispiel[.]test/x.sh".
    authority, separator, path = rest.partition("/")
    return f"{SCHEMES.get(scheme, scheme)}://{authority.replace('.', '[.]')}{separator}{path}"


def defang(text: str) -> str:
    """Macht URLs und IP-Adressen unklickbar."""
    if not text:
        return text
    text = URL.sub(_defang_url, text)
    # Danach die restlichen Adressen. Was in einer URL stand, ist schon
    # entschärft und wird hier nicht mehr getroffen.
    return IPV4.sub(lambda m: m.group(0).replace(".", "[.]"), text)


def shorten(text: str, limit: int) -> str:
    """Kürzt auf ``limit`` Zeichen und macht die Kürzung sichtbar."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
