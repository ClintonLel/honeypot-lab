"""Merker für Weigerungen des Modells (E-045).

Weigert sich das Modell, eine Shell zu spielen, kommt die Weigerung als
normale Antwort (``ok``) beim Angreifer an. Das Gateway liest keine Inhalte
mit, sieht aber die Antwort, bevor es sie weitergibt. Passt sie zu einer der
festen Wendungen unten, steht in ``llm_usage.refusal`` ein ``true``. Nur
dieser Wahrheitswert wird gespeichert, nie Text.

Ein Merker, kein Nachweis: Auch ``echo "I'm sorry"`` zählt mit, und eine
Weigerung in anderen Worten fällt durch. ``python -m app.llm_check`` zählt
die Treffer, das Prüfskript auf dem Sensor (``--filtertest``) zeigt die
Antworten auf eigene Testbefehle im Wortlaut.
"""

from __future__ import annotations

# Anfänge einer Antwort, ohne Groß/Klein, nach führendem Leerraum.
REFUSAL_PREFIXES = (
    "i can't",
    "i cannot",
    "i can not",
    "i won't",
    "i will not",
    "i'm sorry",
    "i am sorry",
    "sorry, i",
    "sorry, but",
    "i apologize",
    "i'm unable",
    "i am unable",
    "i'm not able",
    "i am not able",
    "as an ai",
    "as a language model",
    "i'm an ai",
    "i am an ai",
)

# Wendungen irgendwo in der Antwort. Eine Shell gibt so etwas kaum aus.
REFUSAL_PHRASES = (
    "as an ai",
    "as a language model",
    "i'm an ai",
    "i am an ai",
    "i can't help with",
    "i cannot help with",
    "i can't assist",
    "i cannot assist",
)

# Nur der Anfang wird durchsucht: Eine Weigerung steht vorn, und eine lange
# Ausgabe soll nicht viel Rechenzeit kosten.
SCAN_CHARS = 2_000

# Typografische Apostrophe wie ASCII behandeln.
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})


def looks_like_refusal(content: str) -> bool:
    """``True``, wenn ``content`` zu einer Wendung aus den Listen passt."""
    text = content[:SCAN_CHARS].translate(_APOSTROPHES).lower()
    start = text.lstrip()
    if start.startswith(REFUSAL_PREFIXES):
        return True
    return any(phrase in text for phrase in REFUSAL_PHRASES)
