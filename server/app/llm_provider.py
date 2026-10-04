"""Der Anbieter des LLM-Gateways: Gemini-API, OpenAI-kompatibler Endpunkt (E-045).

Hier steht alles, was an Google hängt: die feste Adresse, die erlaubten
Modelle mit Preisen, die Form der Nachrichten, die Gemini annimmt, und wie
eine Antwort zu lesen ist. Das Gateway (``app.llm_gateway``) prüft vorher die
Anfrage in Cowries Form und setzt Grenzen, Budget und Statuscodes durch.

Quellen, abgerufen am 2026-10-04:

- Endpunkt: https://ai.google.dev/gemini-api/docs/openai (Stand 2026-09-02)
- Preise: https://ai.google.dev/gemini-api/docs/pricing (Stand 2026-10-01)
- Denkmodus: https://ai.google.dev/gemini-api/docs/thinking
- Abschaltungen: https://ai.google.dev/gemini-api/docs/deprecations
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.llm_limits import Prices
from app.llm_request import CheckedRequest

# Fest im Code, nicht konfigurierbar: Der Key geht nur an diese Adresse, und
# nur im Header, nie als ?key= in der URL (die stünde sonst in Logs).
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICES_AS_OF = date(2026, 10, 1)


@dataclass(frozen=True)
class Model:
    """Ein erlaubtes Modell. ``prices`` sind Zeiträume (gültig ab, Preise),
    aufsteigend; die Standard-Stufe, Text, in US-Dollar je Mio. Tokens."""

    prices: tuple[tuple[date, Prices], ...]
    # Erlaubte Werte für reasoning_effort: nur die niedrigsten. Denken kostet
    # wie Ausgabe, dauert und zählt gegen max_tokens (E-045).
    efforts: frozenset[str]

    def prices_on(self, day: date) -> Prices:
        current = self.prices[0][1]
        for start, prices in self.prices:
            if start <= day:
                current = prices
        return current


def _usd(input_: str, cached: str, output: str) -> Prices:
    return Prices(input=Decimal(input_), cached_input=Decimal(cached), output=Decimal(output))


# Feste Modellversionen, kein "-latest" und kein "-preview": Der Name hinter
# einem Alias kann sich während der Laufzeit ändern (method.md 4.5).
MODELS: Mapping[str, Model] = {
    # Gewählt (E-045). Abschaltung frühestens 2027-05-07, nach der Laufzeit.
    "gemini-3.1-flash-lite": Model(
        prices=((date.min, _usd("0.25", "0.025", "1.50")),),
        efforts=frozenset({"minimal", "low"}),
    ),
    "gemini-3.5-flash-lite": Model(
        prices=((date.min, _usd("0.30", "0.03", "2.50")),),
        efforts=frozenset({"minimal", "low"}),
    ),
    # Flash: Preise verdoppeln sich am 2027-01-01.
    "gemini-3.6-flash": Model(
        prices=(
            (date.min, _usd("0.75", "0.075", "3.75")),
            (date(2027, 1, 1), _usd("1.50", "0.15", "7.50")),
        ),
        efforts=frozenset({"minimal", "low"}),
    ),
    # "minimal is not supported and returns an error."
    "gemini-3.8-flash": Model(
        prices=(
            (date.min, _usd("0.75", "0.075", "3.75")),
            (date(2027, 1, 1), _usd("1.50", "0.15", "7.50")),
        ),
        efforts=frozenset({"low"}),
    ),
    # Denken standardmäßig aus; neue Projekte haben laut Google meist keinen
    # Zugriff mehr auf 2.5.
    "gemini-2.5-flash-lite": Model(
        prices=((date.min, _usd("0.10", "0.01", "0.40")),),
        efforts=frozenset({"none", "minimal", "low"}),
    ),
}

ALL_EFFORTS = frozenset().union(*(model.efforts for model in MODELS.values()))


# --- Nachrichten in Geminis Form ---------------------------------------------


def to_gemini(checked: CheckedRequest, merge_turns: bool = False) -> list[dict[str, str]] | None:
    """Die Nachrichten, die an Gemini gehen, oder ``None`` für „leer antworten“.

    Gemini lehnt Anfragen ohne user-Nachricht ab und Nachrichten mit leerem
    Text (E-045). Deshalb:

    - **Exec:** Cowrie hängt den Befehl an den System-Prompt. Er wird dort
      abgetrennt und als user-Nachricht geschickt. Der System-Prompt endet
      dann wie bei einer interaktiven Sitzung und ist in jeder Anfrage gleich
      (Cache); der Befehl steht nur einmal. Der Hash der Persona ist vorher
      auf Cowries Form gebildet und ändert sich dadurch nicht.
    - **Leerer Text im Verlauf** fällt weg. Eine weggelassene leere Antwort
      trägt keine Information.
    - **Leere letzte Zeile** oder Exec ohne Befehl: ``None``. Das Gateway
      antwortet selbst leer, wie eine echte Shell.
    - ``merge_turns``: aufeinanderfolgende Nachrichten derselben Rolle mit
      Zeilenumbruch zusammenfassen, falls Gemini sie ablehnt
      (``LLM_MERGE_TURNS``). Cowrie selbst schickt solche Folgen, wenn eine
      Antwort leer war.
    """
    history = checked.messages[1:]
    if not history:
        if checked.command is None or not checked.command.strip():
            return None
        turns = [{"role": "user", "content": checked.command}]
    else:
        if not history[-1]["content"].strip():
            return None
        turns = [dict(message) for message in history if message["content"].strip()]
    if merge_turns:
        turns = _merged(turns)
    return [{"role": "system", "content": checked.system_head}, *turns]


def _merged(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1] = {"role": turn["role"], "content": merged[-1]["content"] + "\n" + turn["content"]}
        else:
            merged.append(dict(turn))
    return merged


# --- Antworten lesen ---------------------------------------------------------

# Was Cowrie als finish_reason bekommt. Alles andere wird "stop".
COWRIE_FINISH = ("stop", "length")
# Gründe einer Sperre, die in die Logzeile dürfen. Gemini schreibt sie hinter
# "content_filter: " (etwa "content_filter: RECITATION"). Alles andere wird
# "sonst", damit kein freier Text vom Anbieter ins Log gelangt.
BLOCK_REASONS = ("safety", "recitation", "prohibited_content", "blocklist", "spii", "language")


@dataclass(frozen=True)
class Reply:
    """Gelesene Antwort. ``status`` ist ``ok``, ``upstream_blocked`` oder
    ``upstream_error``."""

    status: str
    content: str = ""
    # Für Cowrie: stop oder length.
    finish_reason: str = "stop"
    # Für die Logzeile: stop, length, content_filter oder sonst.
    finish_log: str = "sonst"
    # Grund einer Sperre aus BLOCK_REASONS, "prompt" oder "sonst".
    block: str | None = None


def _finish_log(finish: Any) -> str:
    if not isinstance(finish, str):
        return "sonst"
    lowered = finish.strip().lower()
    if lowered.startswith("content_filter"):
        return "content_filter"
    return lowered if lowered in COWRIE_FINISH else "sonst"


def _block_reason(finish: str) -> str:
    reason = finish.partition(":")[2].strip().lower()
    return reason if reason in BLOCK_REASONS else "sonst"


def _prompt_blocked(payload: dict[str, Any]) -> bool:
    for key in ("prompt_feedback", "promptFeedback"):
        feedback = payload.get(key)
        if isinstance(feedback, dict) and (feedback.get("block_reason") or feedback.get("blockReason")):
            return True
    return False


def read_reply(payload: Any) -> Reply:
    """Liest eine Antwort mit HTTP 200.

    Gesperrt (``upstream_blocked``): ``finish_reason`` beginnt mit
    ``content_filter``, oder es gibt keinen Kandidaten (``choices`` leer), oder
    ein Prompt-Feedback nennt einen Sperrgrund. Wie Gemini eine Sperre über
    den kompatiblen Endpunkt meldet, ist nicht dokumentiert; die Formen
    stammen aus Berichten und aus der nativen API (E-045).
    """
    if not isinstance(payload, dict):
        return Reply("upstream_error")
    if _prompt_blocked(payload):
        return Reply("upstream_blocked", finish_log="content_filter", block="prompt")
    choices = payload.get("choices")
    if isinstance(choices, list) and not choices:
        return Reply("upstream_blocked", finish_log="content_filter", block="prompt")
    if not isinstance(choices, list) or not isinstance(choices[0], dict):
        return Reply("upstream_error")
    finish = choices[0].get("finish_reason")
    finish_log = _finish_log(finish)
    if finish_log == "content_filter":
        return Reply("upstream_blocked", finish_log=finish_log, block=_block_reason(finish))
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return Reply("upstream_error")
    content = message.get("content")
    if content is None:
        # Etwa wenn das Denken max_tokens aufgebraucht hat. Cowrie gibt dann
        # nichts aus; das ist ok mit 0 Zeichen (E-044).
        content = ""
    if not isinstance(content, str):
        return Reply("upstream_error")
    return Reply(
        "ok",
        content=content,
        finish_reason=finish_log if finish_log in COWRIE_FINISH else "stop",
        finish_log=finish_log,
    )
