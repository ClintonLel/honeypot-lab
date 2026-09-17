"""Prüft die Vector-Konfiguration gegen die Grenzen der API und die Regeln.

Vector läuft auf dem Sensor, also auf der Maschine, die als kompromittierbar
gilt. Zwei Zusagen müssen deshalb hier stehen und nicht nur in der Doku: Das
Token steht nicht in der Datei, und die Stapel passen zu dem, was die API und
Caddy annehmen (E-021, E-024).
"""

from __future__ import annotations

from pathlib import Path

import pytest

SENSOR = Path(__file__).resolve().parents[1]
CONFIG = SENSOR / "vector" / "vector.yaml"
COMPOSE = SENSOR / "docker-compose.yml"

# Grenzen der Gegenseite, siehe server/app/events.py und E-021.
API_MAX_EVENTS = 500
CADDY_MAX_BODY = 1024 * 1024


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config() -> dict:
    yaml = pytest.importorskip("yaml", reason="PyYAML fehlt")
    return yaml.safe_load(read(CONFIG))


@pytest.fixture(scope="module")
def compose() -> dict:
    yaml = pytest.importorskip("yaml", reason="PyYAML fehlt")
    return yaml.safe_load(read(COMPOSE))


# --- Secrets ----------------------------------------------------------------


def test_the_token_is_only_a_placeholder():
    """Ohne YAML lesbar, damit dieser Test überall läuft."""
    text = read(CONFIG)
    assert "${INGEST_TOKEN}" in text
    # Ein echtes Token wäre 64 Hex-Zeichen lang.
    assert not any(len(word) >= 64 and all(c in "0123456789abcdef" for c in word) for word in text.split())


def test_the_token_comes_from_the_env_file_on_the_host():
    text = read(COMPOSE)
    assert "/srv/honeypot/.env" in text


# --- Grenzen passen zur Gegenseite ------------------------------------------


def test_a_batch_fits_through_the_api(config):
    batch = config["sinks"]["lab_api"]["batch"]
    assert batch["max_events"] <= API_MAX_EVENTS
    assert batch["max_bytes"] <= CADDY_MAX_BODY


def test_the_sink_points_at_the_lab_api(config):
    sink = config["sinks"]["lab_api"]
    assert sink["uri"] == "https://api.tomkaufmann.dev/ingest"
    assert sink["method"] == "post"
    assert sink["auth"] == {"strategy": "bearer", "token": "${INGEST_TOKEN}"}


def test_a_batch_is_valid_json(config):
    """Aus einzelnen Ereignissen wird ein Array, sonst nimmt die API es nicht."""
    sink = config["sinks"]["lab_api"]
    assert sink["encoding"]["codec"] == "json"
    assert sink["payload_prefix"] == "["
    assert sink["payload_suffix"] == "]"
    assert sink["framing"]["character_delimited"]["delimiter"] == ","


# --- Keine Lücken, keine Duplikate ------------------------------------------


def test_the_position_survives_a_restart(config):
    """Ohne data_dir liest Vector nach einem Neustart alles noch einmal."""
    assert config["data_dir"] == "/var/lib/vector"


def test_the_file_is_recognized_by_its_content(config):
    """Cowrie rotiert die Datei. Am Namen erkannt, gäbe es Lücken."""
    fingerprint = config["sources"]["cowrie"]["fingerprint"]
    assert fingerprint["strategy"] == "checksum"


def test_everything_that_is_already_there_is_read(config):
    assert config["sources"]["cowrie"]["read_from"] == "beginning"


def test_an_outage_is_buffered_on_disk(config):
    buffer = config["sinks"]["lab_api"]["buffer"]
    assert buffer["type"] == "disk"
    assert buffer["when_full"] == "block"
    assert buffer["max_size"] >= 64 * 1024 * 1024


def test_failed_requests_are_retried(config):
    request = config["sinks"]["lab_api"]["request"]
    assert request["retry_attempts"] >= 5


# --- Variante und Mounts ----------------------------------------------------


def test_the_variant_comes_from_the_path(config):
    source = config["transforms"]["aufbereiten"]["source"]
    assert "/srv/honeypot/a/" in source
    assert '.cowrie.variant = "a"' in source
    assert '.cowrie.variant = "b"' in source


def test_every_watched_path_is_mounted(config, compose):
    mounts = compose["services"]["vector"]["volumes"]
    for path in config["sources"]["cowrie"]["include"]:
        directory = str(Path(path).parent)
        assert any(mount.startswith(f"{directory}:") for mount in mounts), f"{directory} fehlt als Mount"


def test_the_logs_are_mounted_read_only(compose):
    mounts = compose["services"]["vector"]["volumes"]
    logs = [m for m in mounts if "/var/log/cowrie" in m]
    assert logs and all(m.endswith(":ro") for m in logs)


def test_vector_sees_neither_host_keys_nor_the_file_system(compose):
    mounts = " ".join(compose["services"]["vector"]["volumes"])
    assert "hostkeys" not in mounts
    assert "fs.pickle" not in mounts


# --- Härtung ----------------------------------------------------------------


def test_the_image_is_pinned(compose):
    assert "@sha256:" in compose["services"]["vector"]["image"]
    assert ":latest" not in compose["services"]["vector"]["image"]


def test_vector_runs_without_root_and_without_capabilities(compose):
    service = compose["services"]["vector"]
    assert service["user"] == "999:999"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]


def test_vector_publishes_no_port(compose):
    service = compose["services"]["vector"]
    assert "ports" not in service
    assert service.get("network_mode") != "host"
