"""Starter für cowrie-b (Schritt 7.3, E-044). Ändert nichts an Cowrie.

Setzt vor dem Start von twistd drei Umgebungsvariablen, die Cowrie liest:

- ``COWRIE_LLM_SYSTEM_PROMPT`` und ``COWRIE_LLM_SYSTEM_PROMPT_EXEC`` aus
  derselben Datei ``prompt.md``. Gleicher Text für Exec und interaktiv, sonst
  zeigt das Gateway zwei Prompt-Hashes und lehnt eine Form ab (E-043). In
  ``cowrie.cfg`` ginge das nicht: ExtendedInterpolation wertet ``$`` aus, und
  configparser entfernt Einrückungen (persona.md).
- ``COWRIE_LLM_API_KEY`` aus der Token-Datei. So steht das Gateway-Token nicht
  in docker-compose.yml und nicht in der Umgebung, die ``docker inspect``
  zeigt.

Danach ersetzt sich der Prozess durch den Befehl aus CMD, wie das ENTRYPOINT
``python3`` im Image von Cowrie.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

PROMPT_PATH = "/cowrie/persona/prompt.md"
TOKEN_PATH = "/run/secrets/llm/llm_gateway_token"
# Das Gateway nimmt kürzere Tokens nicht an (server/app/config.py).
MIN_TOKEN_CHARS = 32


class StartError(Exception):
    """Ohne Prompt oder Token startet cowrie-b nicht. Der Text nennt nie Inhalte."""


def read_prompt(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            prompt = handle.read()
    except OSError as exc:
        raise StartError(f"Prompt nicht lesbar: {path} ({type(exc).__name__})") from None
    if not prompt.strip():
        raise StartError(f"Prompt ist leer: {path}")
    return prompt


def read_token(path: str) -> str:
    try:
        with open(path, encoding="ascii") as handle:
            token = handle.read().rstrip("\r\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise StartError(f"Token nicht lesbar: {path} ({type(exc).__name__})") from None
    if len(token) < MIN_TOKEN_CHARS or not token.isprintable() or any(c.isspace() for c in token):
        raise StartError(f"Token in {path} fehlt oder hat nicht die Form des Gateway-Tokens")
    return token


def build_environment(
    environ: Mapping[str, str], prompt_path: str = PROMPT_PATH, token_path: str = TOKEN_PATH
) -> dict[str, str]:
    prompt = read_prompt(prompt_path)
    env = dict(environ)
    env["COWRIE_LLM_SYSTEM_PROMPT"] = prompt
    env["COWRIE_LLM_SYSTEM_PROMPT_EXEC"] = prompt
    env["COWRIE_LLM_API_KEY"] = read_token(token_path)
    return env


def main(argv: list[str]) -> int:
    if not argv:
        print("Aufruf: launch.py <befehl> [argumente]", file=sys.stderr)
        return 2
    try:
        env = build_environment(os.environ)
    except StartError as exc:
        print(f"cowrie-b startet nicht: {exc}", file=sys.stderr)
        return 1
    os.execve(sys.executable, [sys.executable, *argv], env)
    return 0  # nicht erreicht


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
