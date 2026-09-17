"""Prüft, wie ein Stapel gelesen wird.

Vector kann Ereignisse als JSON-Array oder als eine Zeile je Ereignis senden.
Beides muss ankommen, sonst hängt der Ingest an einer Einstellung auf dem
Sensor (Schritt 4.2).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.ingest import parse_batch


def test_a_json_array_is_a_batch():
    assert parse_batch(b'[{"a": 1}, {"a": 2}]') == [{"a": 1}, {"a": 2}]


def test_an_object_with_events_is_a_batch():
    assert parse_batch(b'{"events": [{"a": 1}]}') == [{"a": 1}]


def test_one_line_per_event_is_a_batch():
    assert parse_batch(b'{"a": 1}\n{"a": 2}\n') == [{"a": 1}, {"a": 2}]


def test_blank_lines_are_ignored():
    assert parse_batch(b'\n{"a": 1}\n{"a": 2}\n\n') == [{"a": 1}, {"a": 2}]


def test_a_single_object_is_a_batch_of_one():
    """In ruhigen Minuten schickt Vector genau ein Ereignis."""
    assert parse_batch(b'{"a": 1}') == [{"a": 1}]


def test_an_empty_body_is_an_empty_batch():
    assert parse_batch(b"") == []
    assert parse_batch(b"   \n") == []


@pytest.mark.parametrize("body", [b'"text"', b"42", b"kaputt", b'{"a": 1}\nkaputt'])
def test_anything_else_is_refused(body: bytes):
    with pytest.raises(HTTPException) as exc:
        parse_batch(body)
    assert exc.value.status_code == 422
