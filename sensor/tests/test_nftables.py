"""Prüft die Umleitung von Port 22 gegen docker-compose.yml und die systemd-Unit."""

from __future__ import annotations

import re
from pathlib import Path

SENSOR = Path(__file__).resolve().parents[1]
RULES = SENSOR / "nftables/honeypot.nft"
UNIT = SENSOR / "systemd/honeypot-nftables.service"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rule_lines() -> list[str]:
    return [line.strip() for line in read(RULES).splitlines() if line.strip() and not line.lstrip().startswith("#")]


def test_rules_never_flush_the_whole_ruleset():
    assert not any("flush ruleset" in line for line in rule_lines())


def test_own_table_replaces_itself_on_reload():
    lines = rule_lines()
    assert lines[:2] == ["table ip honeypot", "delete table ip honeypot"]
    assert "table ip honeypot {" in lines


def test_redirect_targets_cowrie_a_port():
    compose = read(SENSOR / "docker-compose.yml")
    listen_port = re.search(r"COWRIE_SSH_LISTEN_ENDPOINTS: tcp:(\d+):", compose).group(1)
    redirects = [line for line in rule_lines() if "redirect" in line]
    assert redirects == [f"tcp dport 22 redirect to :{listen_port}"]


def test_admin_port_is_not_touched():
    assert "22022" not in read(RULES)


def test_unit_loads_installed_rules_after_network():
    unit = read(UNIT)
    assert "Type=oneshot" in unit
    assert "RemainAfterExit=yes" in unit
    assert "After=network.target" in unit
    assert "ExecStart=/usr/sbin/nft -f /etc/nftables.d/honeypot.nft" in unit
    assert "ExecStop=/usr/sbin/nft delete table ip honeypot" in unit
    assert "WantedBy=multi-user.target" in unit
