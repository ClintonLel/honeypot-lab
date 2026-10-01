"""Probe-Rümpfe für das Ausrollen des LLM-Gateways (app/llm_probe.py)."""

from __future__ import annotations

import json

import pytest

from app.llm_probe import PROBE_COMMAND, PROBE_PERSONA, main, probe_body
from app.llm_request import parse_request, persona_sha256
from tests.cowrie_llm import system_context


def test_both_probes_have_cowries_form_and_the_same_hash():
    exec_checked = parse_request(json.dumps(probe_body("exec")).encode())
    interactive_checked = parse_request(json.dumps(probe_body("interactive")).encode())
    assert exec_checked.persona_sha256 == interactive_checked.persona_sha256 == persona_sha256(PROBE_PERSONA)
    assert len(exec_checked.messages) == 1
    assert [m["role"] for m in interactive_checked.messages] == ["system", "user"]


def test_the_probes_are_built_like_cowrie_builds_them():
    assert probe_body("exec")["messages"][0]["content"] == system_context(
        PROBE_PERSONA, hostname="probe-host", exec_command=PROBE_COMMAND
    )
    assert probe_body("interactive")["messages"][0]["content"] == system_context(
        PROBE_PERSONA, hostname="probe-host"
    )


def test_the_probe_persona_is_long_enough_to_be_cached():
    # Über 1.024 Tokens; bei rund vier Zeichen je Token reichen 6.000 Zeichen sicher.
    assert len(PROBE_PERSONA) > 6_000


def test_the_command_line_prints_json(capsys):
    assert main(["exec"]) == 0
    assert json.loads(capsys.readouterr().out) == probe_body("exec")
    assert main(["anders"]) == 2
    with pytest.raises(ValueError):
        probe_body("anders")
