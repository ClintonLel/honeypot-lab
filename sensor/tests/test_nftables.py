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


def listen_port(service: str) -> str:
    compose = read(SENSOR / "docker-compose.yml")
    block = re.search(rf"^  {service}:\n((?:    .*\n|\n)+)", compose, flags=re.M).group(1)
    return re.search(r"COWRIE_SSH_LISTEN_ENDPOINTS: tcp:(\d+):", block).group(1)


def test_redirect_targets_cowrie_a_port():
    """Bis Schritt 7.4 geht alles an A, B bekommt keinen Verkehr."""
    redirects = [line for line in rule_lines() if "redirect" in line]
    assert redirects == [f"tcp dport 22 redirect to :{listen_port('cowrie-a')}"]


def test_cowrie_b_only_takes_redirected_or_local_connections():
    """2322 nur nach Umleitung oder von lo, sonst verworfen (E-044)."""
    port = listen_port("cowrie-b")
    assert port == "2322"
    lines = rule_lines()
    guard = [line for line in lines if f"dport {port}" in line]
    assert guard == [
        f'tcp dport {port} iif "lo" accept',
        f"tcp dport {port} ct status dnat accept",
        f"tcp dport {port} drop",
    ]
    chain = lines.index("chain input {")
    assert lines[chain + 1] == "type filter hook input priority filter; policy accept;"
    assert lines[chain + 2 : chain + 5] == guard


def test_the_guard_does_not_touch_cowrie_a():
    """Die Sperre gilt nur für B; A bleibt wie in Schritt 2.3."""
    assert not any("2222" in line for line in rule_lines() if "redirect" not in line)


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
