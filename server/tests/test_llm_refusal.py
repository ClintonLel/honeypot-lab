"""Merker für Weigerungen (app/llm_refusal.py, E-045). Alle Antworten erfunden."""

from __future__ import annotations

import pytest

from app.llm_refusal import REFUSAL_PHRASES, REFUSAL_PREFIXES, SCAN_CHARS, looks_like_refusal


@pytest.mark.parametrize(
    "answer",
    [
        "I can't help with that request.",
        "I cannot execute commands on real systems.",
        "I'm sorry, but I can't assist with downloading files.",
        "  \n\nI am sorry, this looks like malware.",
        "Sorry, I can't do that.",
        "As an AI, I don't have a shell.",
        "AS A LANGUAGE MODEL I cannot run xmrig.",
        "I’m sorry, but that is not something I can help with.",
        "I won't run a cryptocurrency miner.",
        "I apologize, but I'm unable to comply.",
        # Mitten im Text, nach einer Ausgabe.
        "bash: line 1: ./x: Permission denied\nNote: as an AI I cannot actually execute this.",
        "Here is the output. I cannot help with mining though.",
    ],
)
def test_refusals_are_recognised(answer):
    assert looks_like_refusal(answer)


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "Linux bld-ci-03 6.12.107+deb13-amd64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux",
        "uid=0(root) gid=0(root) groups=0(root)",
        "bash: xmrig: command not found",
        "--2026-10-14 12:00:00--  http://192.0.2.10/x.sh\nConnecting to 192.0.2.10:80... failed: Connection refused.",
        "Image cannot be found",
        "cannot access 'x': No such file or directory",
    ],
)
def test_shell_output_is_not_a_refusal(answer):
    assert not looks_like_refusal(answer)


def test_an_echo_counts_too():
    """Ein Merker, kein Nachweis (Modul-Docstring)."""
    assert looks_like_refusal("I'm sorry")


def test_only_the_start_of_a_long_answer_is_searched():
    assert not looks_like_refusal("x" * SCAN_CHARS + " as an AI")
    assert looks_like_refusal("x" * (SCAN_CHARS - 20) + " as an AI")


def test_the_lists_are_lowercase_ascii():
    for entry in REFUSAL_PREFIXES + REFUSAL_PHRASES:
        assert entry == entry.lower() and entry.isascii()
