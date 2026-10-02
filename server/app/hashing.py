"""HMAC-SHA256 der Quell-IPs.

Ablauf laut E-009: anreichern, dann hashen, dann den Klartext verwerfen. Der
Schlüssel bleibt über die gesamte Laufzeit derselbe (E-022), damit dieselbe
Adresse immer denselben Hash ergibt und wiederkehrende Angreifer auswertbar
bleiben.

Die Funktionen hier nehmen eine IP entgegen und geben einen Hash zurück. Sie
loggen nichts und werfen keine Ausnahme, die die Adresse enthält.
"""

from __future__ import annotations

import hmac
import ipaddress
from hashlib import sha256


class InvalidAddress(ValueError):
    """Die Eingabe war keine IP-Adresse. Die Eingabe selbst steht nie im Text."""

    def __init__(self) -> None:
        super().__init__("keine gültige IP-Adresse")


def normalize_ip(value: str) -> str:
    """Bringt eine Adresse in ihre kanonische Schreibweise.

    ``2001:DB8::0:1`` und ``2001:db8::1`` sind dieselbe Adresse. Ohne
    Normalisierung bekämen sie verschiedene Hashes und dieselbe Quelle zählte
    doppelt.
    """
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as exc:  # pragma: no cover - Text kommt aus ipaddress
        raise InvalidAddress from exc


def hash_ip(value: str, key: bytes) -> str:
    """Gibt den HMAC-SHA256 der Adresse als Hex zurück."""
    if not key:
        raise ValueError("IP_HMAC_KEY ist leer")
    return hmac.new(key, normalize_ip(value).encode("ascii"), sha256).hexdigest()


# Eigene Domain im selben Schlüssel (E-022): Ein Befehls-Hash kann nie mit
# einem ip_hash übereinstimmen, und es braucht kein weiteres Secret (E-044).
_INPUT_DOMAIN = b"cmd-input\x00"


def input_ref(input_sha256: str, key: bytes) -> str:
    """HMAC über den SHA-256 eines rohen Befehls, als Hex.

    Verknüpft ``commands`` mit ``llm_responses``, ohne dass der Hash selbst
    gespeichert wird. Ein einfacher SHA-256 ließe sich zurückrechnen: Im
    gespeicherten Befehl steht ``<src>`` statt der Adresse, man setzt alle
    Adressen ein und vergleicht. Ohne Schlüssel geht das nicht.
    """
    if not key:
        raise ValueError("IP_HMAC_KEY ist leer")
    return hmac.new(key, _INPUT_DOMAIN + input_sha256.encode("ascii"), sha256).hexdigest()
