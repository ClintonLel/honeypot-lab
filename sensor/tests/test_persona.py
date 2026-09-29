"""Prüft, dass honeyfs, txtcmds, Prozessliste und prompt.md dieselbe Maschine beschreiben."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

PERSONA = Path(__file__).resolve().parents[1] / "persona"
HONEYFS = PERSONA / "honeyfs"
TXTCMDS = PERSONA / "txtcmds"

KERNEL_VERSION = "6.12.107+deb13-amd64"
KERNEL_BUILD = "#1 SMP PREEMPT_DYNAMIC Debian 6.12.107-1 (2026-08-29)"
HOSTNAME = "bld-ci-03"


def load_build():
    spec = importlib.util.spec_from_file_location("persona_build", PERSONA / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_generated_files_are_up_to_date():
    for path, content in load_build().generate().items():
        assert read(path) == content, f"{path.name} veraltet: python3 sensor/persona/build.py ausführen"


def test_every_honeyfs_file_is_verbatim_in_prompt():
    prompt = read(PERSONA / "prompt.md")
    for path in HONEYFS.rglob("*"):
        if path.is_file():
            assert f"~~~\n{read(path)}~~~\n" in prompt, path.relative_to(HONEYFS)


def test_hostname_is_consistent():
    assert read(HONEYFS / "etc/hostname") == f"{HOSTNAME}\n"
    assert f"127.0.1.1\t{HOSTNAME}.build.internal {HOSTNAME}" in read(HONEYFS / "etc/hosts")
    assert f"Hostname set to <{HOSTNAME}>" in read(TXTCMDS / "usr/bin/dmesg")


def test_kernel_strings_are_consistent():
    proc_version = read(HONEYFS / "proc/version")
    assert proc_version.startswith(f"Linux version {KERNEL_VERSION} ")
    assert proc_version.rstrip("\n").endswith(KERNEL_BUILD)
    first_dmesg_line = read(TXTCMDS / "usr/bin/dmesg").splitlines()[0]
    assert first_dmesg_line.endswith(proc_version.rstrip("\n"))
    assert f"Linux {HOSTNAME} {KERNEL_VERSION} {KERNEL_BUILD} x86_64 GNU/Linux" in read(PERSONA / "prompt.md")


def test_cpu_count_is_consistent():
    processors = re.findall(r"^processor\t: \d+$", read(HONEYFS / "proc/cpuinfo"), flags=re.M)
    assert len(processors) == int(read(TXTCMDS / "usr/bin/nproc"))
    assert f"CPU(s):                      {len(processors)}" in read(TXTCMDS / "usr/bin/lscpu")


def test_memory_is_consistent():
    meminfo = dict(re.findall(r"^(\w+):\s+(\d+)", read(HONEYFS / "proc/meminfo"), flags=re.M))
    total_kib = int(meminfo["MemTotal"])
    assert f"MemTotal {total_kib} kB" in read(PERSONA / "prompt.md")
    assert f"{total_kib / 1024:.1f} total" in read(TXTCMDS / "usr/bin/top")
    assert meminfo["SwapTotal"] == "0"


def test_process_list_matches_ps_text():
    rows = read(PERSONA / "ps.txt").splitlines()[1:]
    processes = json.loads(read(PERSONA / "cmdoutput.json"))["command"]["ps"]
    assert [p["PID"] for p in processes] == [int(r.split()[1]) for r in rows]
    top = read(TXTCMDS / "usr/bin/top")
    for process in processes:
        assert re.search(rf"^\s+{process['PID']} ", top, flags=re.M), f"PID {process['PID']} fehlt in top"


def test_accounts_have_homes_and_shadow_entries():
    passwd = [line.split(":") for line in read(HONEYFS / "etc/passwd").splitlines()]
    shadow_users = {line.split(":")[0] for line in read(HONEYFS / "etc/shadow").splitlines()}
    group_names = {line.split(":")[0] for line in read(HONEYFS / "etc/group").splitlines()}
    for name, _x, uid, _gid, _gecos, home, shell in passwd:
        assert name in shadow_users, f"{name} fehlt in /etc/shadow"
        if int(uid) >= 1000 and uid != "65534":
            assert name in group_names, f"Gruppe {name} fehlt"
            assert (HONEYFS / home.lstrip("/")).is_dir(), f"Home von {name} fehlt in honeyfs"
            assert shell == "/bin/bash"


def test_no_real_secrets_in_honeyfs():
    shadow = read(HONEYFS / "etc/shadow")
    assert "$" not in shadow, "honeyfs darf keine Passwort-Hashes enthalten"
    for path in HONEYFS.rglob("*"):
        if path.is_file():
            assert "PRIVATE KEY" not in read(path), path
