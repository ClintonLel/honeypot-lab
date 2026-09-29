"""Prüft, dass cowrie.cfg, userdb.txt und docker-compose.yml zur Persona passen."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

SENSOR = Path(__file__).resolve().parents[1]
PERSONA = SENSOR / "persona"
HONEYFS = PERSONA / "honeyfs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def cowrie_cfg() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    parser.read_string(read(SENSOR / "cowrie/cowrie.cfg"))
    return parser


def compose_volumes(service: str) -> dict[str, str]:
    """Ziel im Container -> Quelle auf dem Host, ohne YAML-Bibliothek gelesen."""
    text = read(SENSOR / "docker-compose.yml")
    block = re.search(rf"^  {service}:\n((?:    .*\n|\n)+)", text, flags=re.M)
    assert block, f"Dienst {service} fehlt in docker-compose.yml"
    volumes = {}
    for source, target in re.findall(r"^      - ([^:\s]+):([^:\s]+)(?::ro)?$", block.group(1), flags=re.M):
        volumes[target] = source
    return volumes


def test_persona_values():
    cfg = cowrie_cfg()
    proc_version = read(HONEYFS / "proc/version")
    prompt = read(PERSONA / "prompt.md")

    assert cfg["honeypot"]["hostname"] == read(HONEYFS / "etc/hostname").strip()
    assert f"Linux version {cfg['shell']['kernel_version']} " in proc_version
    assert proc_version.rstrip("\n").endswith(cfg["shell"]["kernel_build_string"])
    assert f"ssh -V prints exactly: {cfg['shell']['ssh_version']}" in prompt
    banner = cfg["ssh"]["version"].removeprefix("SSH-2.0-")
    assert cfg["shell"]["ssh_version"].startswith(banner + ",")


def test_safety_settings():
    cfg = cowrie_cfg()
    assert cfg.getint("honeypot", "download_limit_size") == 10 * 1024 * 1024
    assert cfg.getboolean("telnet", "enabled") is False
    assert cfg.getboolean("ssh", "forward_redirect") is False
    assert cfg.getboolean("ssh", "forward_tunnel") is False


def test_configured_paths_are_mounted():
    cfg = cowrie_cfg()
    volumes = compose_volumes("cowrie-a")
    paths = [
        cfg["honeypot"]["contents_path"],
        cfg["honeypot"]["txtcmds_path"],
        cfg["shell"]["filesystem"],
        cfg["shell"]["processes"],
        *(cfg["ssh"][key] for key in cfg["ssh"] if key.endswith(("_public_key", "_private_key"))),
    ]
    for path in paths:
        assert any(path == target or path.startswith(target + "/") for target in volumes), path

    assert volumes["/cowrie/cowrie-git/etc"] == "./cowrie"
    assert volumes["/cowrie/persona"] == "./persona"
    for target, source in volumes.items():
        if source.startswith("./"):
            assert (SENSOR / source).is_dir(), source


def test_repo_paths_exist_for_cowrie():
    cfg = cowrie_cfg()
    for key, section in (("contents_path", "honeypot"), ("txtcmds_path", "honeypot"), ("processes", "shell")):
        container_path = cfg[section][key]
        repo_path = PERSONA / container_path.removeprefix("/cowrie/persona/")
        assert repo_path.exists(), f"{key}: {repo_path}"


def test_files_cowrie_reads_as_ascii_are_ascii():
    # Cowrie liest userdb.txt, etc/passwd und etc/group mit encoding="ascii".
    for path in (SENSOR / "cowrie/userdb.txt", HONEYFS / "etc/passwd", HONEYFS / "etc/group"):
        path.read_bytes().decode("ascii")


def test_userdb_accounts_exist_in_persona():
    passwd = {line.split(":")[0]: line.split(":") for line in read(HONEYFS / "etc/passwd").splitlines()}
    users = set()
    for line in read(SENSOR / "cowrie/userdb.txt").splitlines():
        if not line or line.startswith("#"):
            continue
        user, placeholder, _password = line.split(":", 2)
        assert placeholder == "x"
        users.add(user)
    assert users == {"root", "admin"}
    for user in users:
        assert passwd[user][6] == "/bin/bash", user


def test_image_is_pinned_by_tag_and_digest():
    """Tag mit Versionsnummer und Digest, kein :latest (E-010).

    Der Tag darf einen Zusatz tragen, etwa ``0.58.0-alpine``.
    """
    images = re.findall(r"^\s*image:\s*(\S+)\s*$", read(SENSOR / "docker-compose.yml"), flags=re.M)
    assert images
    for image in images:
        assert re.fullmatch(r"[\w./-]+:\d+\.\d+\.\d+(-[\w.]+)?@sha256:[0-9a-f]{64}", image), image


def test_debian_base_image_is_pinned():
    first_from = re.search(r"^FROM\s+(\S+)", read(PERSONA / "rootfs/Dockerfile"), flags=re.M).group(1)
    assert re.fullmatch(r"debian:trixie-\d{8}@sha256:[0-9a-f]{64}", first_from), first_from
