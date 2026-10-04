"""Rümpfe für Probeaufrufe des LLM-Gateways (Schritt 7.2, server/README.md).

Gibt eine Anfrage in der Form aus, die Cowrie 3.0.14 schickt, als JSON auf
stdout. Damit lässt sich das Gateway nach dem Ausrollen von Hand prüfen, ohne
cowrie-b:

    python -m app.llm_probe exec          # nur die System-Nachricht
    python -m app.llm_probe interactive   # System-Nachricht und ein Befehl
    python -m app.llm_probe verlauf       # Verlauf mit leerer Antwort (E-045)
    python -m app.llm_probe leer          # leere Zeile, ohne Anbieter

Alle nutzen dieselbe Probe-Persona und zeigen deshalb im Log denselben
``prompt_sha256``. Die Persona ist lang genug (über 4.096 Tokens), dass der
Anbieter sie zwischenspeichert; der zweite Aufruf zeigt dann
``cached_tokens``. Sie enthält keinen Text von Angreifern und nichts über den
Sensor.

``verlauf`` prüft am echten Anbieter, was nur dort zu sehen ist: Nach dem
Weglassen der leeren Antwort folgen zwei user-Nachrichten aufeinander, und
die frühere Antwort kommt ohne Gemini-Signatur zurück. Scheitert sie mit 502
(im Log ``upstream_status`` 400), gehört ``LLM_MERGE_TURNS=true`` in die
``.env`` (server/README.md).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from app.llm_request import COWRIE_GUIDANCE

# Fülltext, damit der gleichbleibende Anfang über 4.096 Tokens kommt, die
# Untergrenze für Geminis Cache (E-045).
_PADDING = "\n".join(
    f"- /srv/probe/file-{n:03d}.txt contains exactly one line: probe file {n}"
    for n in range(1, 361)
)

PROBE_PERSONA = (
    "You are the bash shell of the Linux server probe-host. Every user message is a"
    " command line typed into an SSH session on this server. Reply with exactly the"
    " text the terminal would print, without explanations or markdown.\n"
    "# Files\n" + _PADDING + "\n"
)

PROBE_COMMAND = "echo gateway-probe-ok"


def _system(exec_command: str = "") -> str:
    # Wie cowrie/llm/protocol.py, _build_system_context (3.0.14).
    context = PROBE_PERSONA + COWRIE_GUIDANCE
    context += " The hostname is 'probe-host' and username is 'root'. The current working directory is '/'."
    if exec_command:
        context += f" The command to execute is: {exec_command}"
    return context


KINDS = ("exec", "interactive", "verlauf", "leer")


def probe_body(kind: str) -> dict[str, Any]:
    """Eine der Formen aus ``KINDS``. Modell und Grenzen setzt das Gateway."""
    if kind == "exec":
        messages = [{"role": "system", "content": _system(PROBE_COMMAND)}]
    elif kind == "interactive":
        messages = [
            {"role": "system", "content": _system()},
            {"role": "user", "content": PROBE_COMMAND},
        ]
    elif kind == "verlauf":
        messages = [
            {"role": "system", "content": _system()},
            {"role": "user", "content": "echo probe-first"},
            {"role": "assistant", "content": "probe-first"},
            {"role": "user", "content": "cd /srv/probe"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": PROBE_COMMAND},
        ]
    elif kind == "leer":
        messages = [
            {"role": "system", "content": _system()},
            {"role": "user", "content": ""},
        ]
    else:
        raise ValueError("|".join(KINDS))
    return {"model": "vom-gateway-ersetzt", "messages": messages, "max_tokens": 50, "temperature": 0.7}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in KINDS:
        print(f"Aufruf: python -m app.llm_probe {'|'.join(KINDS)}", file=sys.stderr)
        return 2
    print(json.dumps(probe_body(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
