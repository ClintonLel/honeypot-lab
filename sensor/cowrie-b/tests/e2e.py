"""End-to-End-Test von cowrie-b in Containern (Schritt 7.3, CI-Job cowrie-b).

Startet auf dem Runner mit Docker, alle mit Host-Netz und nur auf 127.0.0.1:

    gateway  fake_gateway.py aus dem Image von cowrie-b   :18080
    a        Image von A, Backend shell                   :2222
    b        Image von cowrie-b, Backend llm, gepatcht    :2322
    u        Image von A, Backend llm, ungepatcht         :2422

Alle mit unserer cowrie.cfg und Persona, gehärtet wie in docker-compose.yml.
Als Dateisystem dient das fs.pickle aus dem Image. B startet über launch.py
mit Token-Datei und prompt.md.

Prüft:
1. Parität A ↔ B: dieselben Eingaben ergeben dieselbe Folge von
   cowrie.command.input (Anzahl und input). Einzige Ausnahme ist stdin für
   eine Exec-Shell, ein bekannter Unterschied (E-044); sein Fall schreibt ihn
   fest.
2. In B je Befehl genau ein cowrie.llm.response mit passendem Index und Hash,
   gleiche motd wie A, Ausgabe auch bei EOF.
3. Ausgabe wie ohne Patch: B und U zeigen dem Client bei jedem Ausgang des
   Gateways dieselben Bytes und denselben Exit-Status.

Die Logs heißen hier lab-events.jsonl, nicht cowrie.json: Es sind erfundene
Testsitzungen, keine Rohdaten. Ausgegeben werden nur Zähler und OK/FEHLER.

    python3 sensor/cowrie-b/tests/e2e.py --image localhost/honeypot-lab/cowrie-b:ci
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SENSOR = HERE.parents[1]
spec = importlib.util.spec_from_file_location("check_cowrie_b", SENSOR / "scripts" / "check-cowrie-b.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

LOG = "var/log/cowrie/lab-events.jsonl"
PORTS = {"gateway": 18080, "a": 2222, "b": 2322, "u": 2422}
HARDENING = [
    "--network", "host", "--read-only", "--tmpfs", "/tmp:size=64m,mode=1777",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "999:999",
]

PARITY: list[dict[str, Any]] = [
    {"name": "exec-einzeilig", "exec": ["uname -a"]},
    {"name": "exec-mehrzeilig", "exec": ["uname -a\nid"]},
    {"name": "exec-semikolon", "exec": ["cd /tmp; ls; id"]},
    {"name": "exec-leer", "exec": [""]},
    {"name": "exec-8192", "exec": ["echo " + "A" * 8187]},
    {"name": "exec-eof", "exec": ["uname -a"], "eof": True},
    {"name": "parallel", "exec": ["uname -a", "id"]},
    {"name": "interaktiv", "shell": ["uname -a", "", "id", "cd /tmp; ls"]},
    {"name": "stdin-shell", "exec": ["sh"], "stdin": "id\nuname -a\n"},
]
# Bekannter Unterschied 1 (E-044): A führt stdin einer Exec-Shell Zeile für
# Zeile aus, B schickt nur den Befehl ans Modell.
EXPECTED_DIFFERENCE = {"stdin-shell": (["sh", "id", "uname -a"], ["sh"])}

# Was das Fake-Gateway liefert, und wie B es einordnen muss.
OUTPUTS: list[tuple[dict[str, Any], list[tuple[str, int | None]]]] = [
    ({"name": "ok", "exec": ["uname -a"]}, [("ok", 200)]),
    ({"name": "leer", "exec": ["lab-empty"]}, [("ok", 200)]),
    ({"name": "429", "exec": ["lab-status-429"]}, [("rate_limited", 429)]),
    ({"name": "500", "exec": ["lab-status-500"]}, [("error", 500)]),
    ({"name": "502", "exec": ["lab-status-502"]}, [("upstream_error", 502)]),
    ({"name": "503", "exec": ["lab-status-503"]}, [("unavailable", 503)]),
    ({"name": "504", "exec": ["lab-status-504"]}, [("timeout", 504)]),
    ({"name": "abbruch", "exec": ["lab-close"]}, [("error", None)]),
    ({"name": "kein-json", "exec": ["lab-bad"]}, [("error", 200)]),
    (
        {"name": "interaktiv", "shell": ["uname -a", "lab-empty", "lab-status-429", "lab-status-503", "lab-close", "lab-bad", ""]},
        [("ok", 200), ("ok", 200), ("rate_limited", 429), ("unavailable", 503), ("error", None), ("error", 200), ("ok", 200)],
    ),
]


def docker(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, **kwargs)


def image_of_a() -> str:
    compose = (SENSOR / "docker-compose.yml").read_text(encoding="utf-8")
    return re.search(r"^x-cowrie: &cowrie\n  image: (\S+)$", compose, flags=re.M).group(1)


def prepare(work: Path) -> None:
    keys = work / "hostkeys"
    keys.mkdir()
    for kind in ("rsa", "ecdsa", "ed25519"):
        subprocess.run(["ssh-keygen", "-q", "-t", kind, "-N", "", "-C", "", "-f", str(keys / f"ssh_host_{kind}_key")], check=True)
    for path in keys.iterdir():
        path.chmod(0o644)  # Nur im Test: uid 999 im Container muss lesen.
    for name in ("a", "b", "u"):
        for sub in ("var/log/cowrie", "var/lib/cowrie/tty", "var/lib/cowrie/downloads"):
            (work / name / sub).mkdir(parents=True)
        for root, dirs, _ in os.walk(work / name):
            os.chmod(root, 0o777)
    secrets = work / "secrets"
    secrets.mkdir()
    (secrets / "llm_gateway_token").write_text("t" * 48 + "\n", encoding="ascii")
    (secrets / "llm_gateway_token").chmod(0o644)


def cowrie(name: str, image: str, work: Path, env: dict[str, str], extra: list[str] | None = None, pass_env: dict[str, str] | None = None) -> None:
    args = ["run", "-d", "--name", f"lab-{name}", *HARDENING]
    for key, value in {
        "COWRIE_SHELL_FILESYSTEM": "/cowrie/cowrie-git/src/cowrie/data/fs.pickle",
        "COWRIE_OUTPUT_JSONLOG_LOGFILE": LOG,
        **env,
    }.items():
        args += ["-e", f"{key}={value}"]
    for key in pass_env or {}:
        args += ["-e", key]  # Wert aus der Umgebung von docker, nicht aus argv
    args += [
        "-v", f"{SENSOR / 'cowrie'}:/cowrie/cowrie-git/etc:ro",
        "-v", f"{SENSOR / 'persona'}:/cowrie/persona:ro",
        "-v", f"{work / 'hostkeys'}:/cowrie/hostkeys:ro",
        "-v", f"{work / name / 'var'}:/cowrie/cowrie-git/var",
        *(extra or []),
        image,
    ]
    docker(*args, env={**os.environ, **(pass_env or {})})


def wait_for(port: int, timeout: float = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def drive(image: str, port: int, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = docker(
        "run", "--rm", "-i", *HARDENING, "--entrypoint", "/cowrie/cowrie-env/bin/python3",
        image, "/cowrie/lab/sshdrive.py", "--port", str(port), "--timeout", "30",
        input=json.dumps(plan), timeout=900,
    ).stdout
    return json.loads(out)


def sessions(work: Path, name: str) -> list[list[dict[str, Any]]]:
    """Sitzungen in der Reihenfolge ihres Beginns."""
    path = work / name / LOG
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    order: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        sid = event.get("session")
        if event.get("eventid") == "cowrie.session.connect":
            order.append(sid)
        grouped.setdefault(sid, []).append(event)
    return [grouped[sid] for sid in order]


def inputs(session_events: list[dict[str, Any]]) -> list[str]:
    return [e["input"] for e in session_events if e.get("eventid") == "cowrie.command.input"]


def responses(session_events: list[dict[str, Any]]) -> list[tuple[str, int | None]]:
    found = sorted(
        (e for e in session_events if e.get("eventid") == "cowrie.llm.response"), key=lambda e: e["command_index"]
    )
    return [(e["outcome"], e["http_status"]) for e in found]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="gebautes Image von cowrie-b")
    args = parser.parse_args()
    image_a = image_of_a()
    work = Path(tempfile.mkdtemp(prefix="lab-e2e-"))
    checks: list[tuple[str, bool]] = []
    names = ["gateway", "a", "b", "u"]
    try:
        prepare(work)
        docker(
            "run", "-d", "--name", "lab-gateway", *HARDENING, "--entrypoint", "/cowrie/cowrie-env/bin/python3",
            "-v", f"{HERE}:/lab-tests:ro", args.image, "/lab-tests/fake_gateway.py", "--port", str(PORTS["gateway"]),
        )
        llm = {
            "COWRIE_HONEYPOT_BACKEND": "llm",
            "COWRIE_LLM_HOST": f"http://127.0.0.1:{PORTS['gateway']}",
            "COWRIE_LLM_PATH": "/v1/chat/completions",
            "COWRIE_LLM_DEBUG": "false",
        }
        cowrie("a", image_a, work, {
            "COWRIE_HONEYPOT_SENSOR_NAME": "hp-a", "COWRIE_HONEYPOT_BACKEND": "shell",
            "COWRIE_SSH_LISTEN_ENDPOINTS": f"tcp:{PORTS['a']}:interface=127.0.0.1",
        })
        cowrie("b", args.image, work, {
            **llm, "COWRIE_HONEYPOT_SENSOR_NAME": "hp-b", "COWRIE_LLM_REQUEST_TIMEOUT": "20",
            "COWRIE_SSH_LISTEN_ENDPOINTS": f"tcp:{PORTS['b']}:interface=127.0.0.1",
        }, extra=["-v", f"{work / 'secrets'}:/run/secrets/llm:ro"])
        prompt = (SENSOR / "persona" / "prompt.md").read_text(encoding="utf-8")
        cowrie("u", image_a, work, {
            **llm, "COWRIE_HONEYPOT_SENSOR_NAME": "hp-u",
            "COWRIE_SSH_LISTEN_ENDPOINTS": f"tcp:{PORTS['u']}:interface=127.0.0.1",
        }, pass_env={
            "COWRIE_LLM_API_KEY": "t" * 48,
            "COWRIE_LLM_SYSTEM_PROMPT": prompt,
            "COWRIE_LLM_SYSTEM_PROMPT_EXEC": prompt,
        })
        up = {name: wait_for(port) for name, port in PORTS.items()}
        checks.append((f"Container erreichbar: {sum(up.values())} von {len(up)}", all(up.values())))
        if not all(up.values()):
            return finish(checks, names)

        # 1 und 2: Parität A ↔ B, Paarung in B
        drive_a = drive(args.image, PORTS["a"], PARITY)
        drive_b = drive(args.image, PORTS["b"], PARITY)
        time.sleep(1)
        log_a, log_b = sessions(work, "a"), sessions(work, "b")
        checks.append((f"Sitzungen A {len(log_a)}, B {len(log_b)}, erwartet je {len(PARITY)}", len(log_a) == len(log_b) == len(PARITY)))
        for step, sa, sb in zip(PARITY, log_a, log_b):
            name = step["name"]
            if name in EXPECTED_DIFFERENCE:
                want_a, want_b = EXPECTED_DIFFERENCE[name]
                checks.append((f"{name}: bekannter Unterschied besteht wie beschrieben", inputs(sa) == want_a and inputs(sb) == want_b))
            else:
                checks.append((f"{name}: command.input gleich in A und B ({len(inputs(sa))})", inputs(sa) == inputs(sb)))
            paired = check.pairing(sb)
            checks.append((
                f"{name}: B je Befehl genau ein llm.response, Index und Hash passen",
                paired["aufrufe"] == paired["befehle"] and paired["index_ok"] and paired["hash_ok"] and paired["reihenfolge_ok"],
            ))
            checks.append((f"{name}: B alle Aufrufe ok, Client nicht weg", set(paired["outcomes"]) == {"ok"} and paired["client_gone"] == 0))
        motd = check.motd_digest((SENSOR / "persona/honeyfs/etc/motd").read_bytes())
        shells = [r for r in drive_a + drive_b if "motd_sha256" in r]
        checks.append(("motd in A und B gleich und wie persona/honeyfs/etc/motd", len(shells) == 2 and all(r["motd_sha256"] == motd for r in shells)))
        for result_a, result_b in zip(drive_a, drive_b):
            if result_a["name"] == "exec-eof":
                checks.append((
                    "exec-eof: A und B zeigen eine Ausgabe",
                    result_a["kanaele"][0]["bytes"] > 0 and result_b["kanaele"][0]["bytes"] > 0,
                ))

        # 3: Ausgabe wie ohne Patch, B gegen U
        plan = [step for step, _ in OUTPUTS]
        drive_b = drive(args.image, PORTS["b"], plan)
        drive_u = drive(args.image, PORTS["u"], plan)
        time.sleep(1)
        log_b = sessions(work, "b")[len(PARITY):]
        for (step, expected), result_b, result_u, sb in zip(OUTPUTS, drive_b, drive_u, log_b):
            same = [(k["exit"], k["sha256"]) for k in result_b["kanaele"]] == [(k["exit"], k["sha256"]) for k in result_u["kanaele"]]
            checks.append((f"{step['name']}: Ausgabe beim Client wie ohne Patch", same and result_b["fertig"] and result_u["fertig"]))
            checks.append((f"{step['name']}: Ausgang in B {responses(sb)}", responses(sb) == expected))
        return finish(checks, names)
    finally:
        for name in names:
            subprocess.run(["docker", "rm", "-f", f"lab-{name}"], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)


def finish(checks: list[tuple[str, bool]], names: list[str]) -> int:
    ok = check.report(checks)
    if not ok:
        # Nur Cowries Textlog der Test-Container, ohne Prompts (debug aus).
        for name in names:
            logs = subprocess.run(["docker", "logs", "--tail", "40", f"lab-{name}"], capture_output=True, text=True)
            print(f"--- lab-{name}\n{logs.stdout[-4000:]}{logs.stderr[-4000:]}")
    print("Ergebnis:", "OK" if ok else "FEHLER")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
