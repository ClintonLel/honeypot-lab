#!/usr/bin/env python3
"""Erzeugt die abgeleiteten Persona-Dateien aus ihren Quellen.

Quellen (von Hand gepflegt):
  prompt.template.md   Text des System-Prompts mit Markern
  honeyfs/             Dateiinhalte für Cowrie
  txtcmds/             feste Befehlsausgaben für Cowrie
  ps.txt               Prozessliste im Format von ps aux

Erzeugt:
  prompt.md                   System-Prompt für cowrie-b
  cmdoutput.json              Prozessliste für cowrie-a ([shell] processes)
  txtcmds/usr/bin/mount       aus honeyfs/proc/mounts
  txtcmds/usr/sbin/lsmod      aus honeyfs/proc/modules

Aufruf:
  python3 sensor/persona/build.py           schreibt die Dateien
  python3 sensor/persona/build.py --check   prüft nur, ob sie aktuell sind
"""

from __future__ import annotations

import json
import string
import sys
from pathlib import Path

PERSONA = Path(__file__).resolve().parent
HONEYFS = PERSONA / "honeyfs"
TXTCMDS = PERSONA / "txtcmds"

# Reihenfolge der Dateien im Prompt. Jede honeyfs-Datei muss hier stehen.
FILE_ORDER = [
    "etc/hostname",
    "etc/hosts",
    "etc/resolv.conf",
    "etc/issue",
    "etc/issue.net",
    "etc/motd",
    "etc/debian_version",
    "usr/lib/os-release",
    "proc/version",
    "proc/cpuinfo",
    "proc/meminfo",
    "proc/modules",
    "proc/mounts",
    "etc/passwd",
    "etc/group",
    "etc/shadow",
    "etc/sudoers.d/90-admin",
    "etc/cron.d/build-cleanup",
    "etc/systemd/system/ci-agent.service",
    "etc/systemd/system/artifact-sync.service",
    "etc/systemd/system/artifact-sync.timer",
    "opt/ci-agent/README.txt",
    "opt/ci-agent/VERSION",
    "opt/ci-agent/bin/ci-agent",
    "opt/ci-agent/etc/agent.ini",
    "home/admin/.bash_history",
    "home/admin/runbook.txt",
    "home/builder/.gitconfig",
    "home/release/.ssh/config",
]

# Befehle, deren feste Ausgabe wörtlich im Prompt steht: (Aufruf, txtcmds-Pfad)
PROMPT_COMMANDS = [
    ("df -h", "usr/bin/df"),
    ("dmesg", "usr/bin/dmesg"),
    ("lscpu", "usr/bin/lscpu"),
    ("nproc", "usr/bin/nproc"),
    ("top -bn1", "usr/bin/top"),
]

# txtcmds, die nicht wörtlich im Prompt stehen. mount und lsmod beschreibt der
# Prompt als abgeleitet, die übrigen korrigieren nur Cowries Standardausgaben.
NOT_IN_PROMPT = {
    "usr/bin/mount",
    "usr/sbin/lsmod",
    "usr/bin/getconf",
    "usr/bin/nano",
    "usr/bin/stty",
    "usr/bin/sync",
}

# Cowrie setzt den Prompt per str.format_map ein. Nur diese Felder sind erlaubt.
ALLOWED_FIELDS = {"ip", "ip6"}

FENCE = "~~~"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def relfiles(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def fenced(content: str) -> str:
    if FENCE in content:
        raise ValueError(f"Inhalt enthält den Zaun {FENCE}")
    note = "This file exists and is empty (0 bytes).\n\n" if not content else ""
    return f"{note}{FENCE}\n{content}{FENCE}\n"


def mount_output(proc_mounts: str) -> str:
    lines = []
    for line in proc_mounts.splitlines():
        device, target, fstype, options, _dump, _pass = line.split()
        lines.append(f"{device} on {target} type {fstype} ({options})")
    return "\n".join(lines) + "\n"


def lsmod_output(proc_modules: str) -> str:
    lines = ["Module                  Size  Used by"]
    for line in proc_modules.splitlines():
        name, size, used, holders = line.split()[:4]
        row = f"{name:<19} {int(size):>8}  {used}"
        if holders != "-":
            row += " " + holders.rstrip(",")
        lines.append(row)
    return "\n".join(lines) + "\n"


def cmdoutput(ps_text: str) -> str:
    lines = ps_text.splitlines()
    if not lines[0].startswith("USER "):
        raise ValueError("ps.txt muss mit der Kopfzeile von ps aux beginnen")
    processes = []
    for line in lines[1:]:
        user, pid, cpu, mem, vsz, rss, tty, stat, start, time, command = line.split(None, 10)
        processes.append(
            {
                "COMMAND": command,
                "CPU": float(cpu),
                "MEM": float(mem),
                "PID": int(pid),
                "RSS": int(rss),
                "START": start,
                "STAT": stat,
                "TIME": time,
                "TTY": tty,
                "USER": user,
                "VSZ": int(vsz),
            }
        )
    return json.dumps({"command": {"ps": processes}}, indent=2, ensure_ascii=False) + "\n"


def prompt(template: str, ps_text: str) -> str:
    missing = relfiles(HONEYFS) ^ set(FILE_ORDER)
    if missing:
        raise ValueError(f"honeyfs und FILE_ORDER passen nicht zusammen: {sorted(missing)}")

    files = "".join(f"## /{rel}\n\n{fenced(read(HONEYFS / rel))}\n" for rel in FILE_ORDER)
    commands = "".join(f"## {call}\n\n{fenced(read(TXTCMDS / rel))}\n" for call, rel in PROMPT_COMMANDS)

    text = template
    for marker, value in (
        ("@@PROCESSES@@\n", ps_text),
        ("@@FILES@@\n", files),
        ("@@COMMANDS@@\n", commands),
    ):
        if text.count(marker) != 1:
            raise ValueError(f"Marker {marker.strip()} muss genau einmal vorkommen")
        text = text.replace(marker, value)

    fields = {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    if not fields <= ALLOWED_FIELDS:
        raise ValueError(f"Unerlaubte Format-Felder im Prompt: {sorted(fields - ALLOWED_FIELDS)}")
    return text


def generate() -> dict[Path, str]:
    """Alle abgeleiteten Dateien mit ihrem Soll-Inhalt."""
    ps_text = read(PERSONA / "ps.txt")
    outputs = {
        TXTCMDS / "usr/bin/mount": mount_output(read(HONEYFS / "proc/mounts")),
        TXTCMDS / "usr/sbin/lsmod": lsmod_output(read(HONEYFS / "proc/modules")),
        PERSONA / "cmdoutput.json": cmdoutput(ps_text),
        PERSONA / "prompt.md": prompt(read(PERSONA / "prompt.template.md"), ps_text),
    }

    in_prompt = {rel for _, rel in PROMPT_COMMANDS}
    known = in_prompt | NOT_IN_PROMPT
    present = relfiles(TXTCMDS) | {p.relative_to(TXTCMDS).as_posix() for p in outputs if TXTCMDS in p.parents}
    if present != known:
        raise ValueError(f"txtcmds nicht zugeordnet: {sorted(present ^ known)}")
    return outputs


def main(argv: list[str]) -> int:
    check = "--check" in argv
    outdated = []
    for path, content in generate().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if check:
            outdated.append(path.relative_to(PERSONA).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"geschrieben: {path.relative_to(PERSONA)}")
    if outdated:
        print("Nicht aktuell, bitte build.py ausführen:", ", ".join(outdated), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
