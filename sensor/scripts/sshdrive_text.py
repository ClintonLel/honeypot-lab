"""sshdrive.py mit dem Anfang der Ausgabe, nur für ``check-cowrie-b.py --filtertest``.

``/cowrie/lab/sshdrive.py`` im Image von cowrie-b gibt bewusst nur Länge und
SHA-256 der Ausgabe zurück: Antworten des Modells gehören nicht ins Terminal
(method.md 9.7, E-042). Für den Filtertest (E-045) sieht Tom die Antworten auf
unsere eigenen, harmlosen Testbefehle doch, um Weigerungen und Sperren selbst
zu erkennen. Dafür ergänzt dieser Wrapper je Kanal ``text``: die ersten
``TEXT_CHARS`` Zeichen der Ausgabe ohne Steuerfolgen des Terminals. Kürzen,
Säubern und Entschärfen macht das Prüfskript auf dem Host.

Der Wrapper liegt nicht im Image, damit cowrie-b dafür nicht neu gebaut wird.
Das Prüfskript hängt ihn read-only in den Container und startet ihn mit dem
Python des Images (Twisted). Er ändert nichts an sshdrive.py selbst.
"""

from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, "/cowrie/lab")

import sshdrive  # noqa: E402

# Mehr als das Prüfskript zeigt (200), damit Kürzen dort sichtbar wird.
TEXT_CHARS = 2_000

_without_text = sshdrive.channel_result


def channel_result(chan: Any, data: bytes) -> dict[str, Any]:
    result = _without_text(chan, data)
    # Höchstens vier Byte je Zeichen in UTF-8.
    result["text"] = sshdrive.normalized(data[: TEXT_CHARS * 4]).decode("utf-8", "replace")[:TEXT_CHARS]
    return result


sshdrive.channel_result = channel_result

if __name__ == "__main__":
    sshdrive.main()
