"""``python -m app.llm_check`` ohne Datenbank: nur die Befehlszeile.

Mit Datenbank: ``tests/test_ingest_llm.py``.
"""

from __future__ import annotations

import pytest

from app import llm_check


def test_an_unknown_option_exits_with_2(capsys):
    with pytest.raises(SystemExit) as caught:
        llm_check.main(["--unbekannt"])
    assert caught.value.code == 2
    assert capsys.readouterr().out == ""


def test_days_must_be_a_number():
    with pytest.raises(SystemExit) as caught:
        llm_check.main(["--tage", "gestern"])
    assert caught.value.code == 2
