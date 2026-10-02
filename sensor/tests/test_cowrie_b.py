"""Prüft cowrie-b: Dienst, Image, Patch, Starter und dass A gleich bleibt (7.3).

Der Patch selbst wird im gebauten Image getestet (``sensor/cowrie-b/tests``,
CI-Job ``cowrie-b``). Hier steht, was ohne Cowrie prüfbar ist.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

SENSOR = Path(__file__).resolve().parents[1]
COWRIE_B = SENSOR / "cowrie-b"
COMPOSE = SENSOR / "docker-compose.yml"
A_IMAGE = "cowrie/cowrie:3.0.14@sha256:f6ea2e847a1837794cd570322a25a9da819824c70a718600fa6de4c1eba66626"

# Obergrenze der Persona samt eingesetzter Adressen. Die Größentests des
# Gateways rechnen damit (server/tests/cowrie_llm.py, PERSONA_MAX_CHARS).
PERSONA_MAX_CHARS = 32_000
# Längste Schreibweise einer IPv4- und einer IPv6-Adresse.
LONGEST_IP = "255.255.255.255"
LONGEST_IP6 = "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launch = load("launch", COWRIE_B / "lab" / "launch.py")
lockcheck = load("lockcheck", COWRIE_B / "lab" / "lockcheck.py")


@pytest.fixture(scope="module")
def compose() -> dict:
    yaml = pytest.importorskip("yaml", reason="PyYAML fehlt")
    return yaml.safe_load(read(COMPOSE))


# --- A bleibt, wie es ist ------------------------------------------------------
#
# Während der Laufzeit darf sich an A nichts ändern (method.md 4.5). Diese
# Werte sind der Stand vor Schritt 7.3. Eine gewollte Änderung an A ändert
# auch diesen Test, und das soll auffallen.

COWRIE_CFG_SHA256 = "a5830bd98c4e0e083b7f2fcb61c87fd68d40eacb0a2049ab7ab47c3055eee1b7"
USERDB_SHA256 = "e643e03474f608bd5dde474e1371fe0d91e4278e731de96ee00050d80d0025ab"

HARDENING = {
    "image": A_IMAGE,
    "network_mode": "host",
    "user": "999:999",
    "read_only": True,
    "tmpfs": ["/tmp:size=64m,mode=1777"],
    "security_opt": ["no-new-privileges:true"],
    "cap_drop": ["ALL"],
    "mem_limit": "512m",
    "pids_limit": 256,
    "cpus": 1.0,
    "restart": "unless-stopped",
    "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
}

COWRIE_A = {
    **HARDENING,
    "container_name": "cowrie-a",
    "environment": {
        "COWRIE_HONEYPOT_SENSOR_NAME": "hp-a",
        "COWRIE_HONEYPOT_BACKEND": "shell",
        "COWRIE_SSH_LISTEN_ENDPOINTS": "tcp:2222:interface=0.0.0.0",
    },
    "volumes": [
        "./cowrie:/cowrie/cowrie-git/etc:ro",
        "./persona:/cowrie/persona:ro",
        "/srv/honeypot/persona/fs.pickle:/cowrie/fs.pickle:ro",
        "/srv/honeypot/hostkeys:/cowrie/hostkeys:ro",
        "/srv/honeypot/a/var:/cowrie/cowrie-git/var",
    ],
}


def test_cowrie_a_is_unchanged(compose):
    assert compose["x-cowrie"] == HARDENING
    assert compose["services"]["cowrie-a"] == COWRIE_A


def test_the_shared_configuration_is_unchanged():
    """cowrie.cfg gilt für A und B. Was nur B betrifft, steht in Compose."""
    assert hashlib.sha256((SENSOR / "cowrie/cowrie.cfg").read_bytes()).hexdigest() == COWRIE_CFG_SHA256
    assert hashlib.sha256((SENSOR / "cowrie/userdb.txt").read_bytes()).hexdigest() == USERDB_SHA256
    assert "[llm]" not in read(SENSOR / "cowrie/cowrie.cfg")


# --- Der Dienst cowrie-b ----------------------------------------------------------


def test_cowrie_b_differs_from_a_only_where_it_must(compose):
    a = compose["services"]["cowrie-a"]
    b = compose["services"]["cowrie-b"]
    for key, value in HARDENING.items():
        if key != "image":
            assert b[key] == value, key
    # Gleiche Einbindungen bis auf die eigenen Daten und das Token.
    assert b["volumes"] == [v.replace("/srv/honeypot/a/", "/srv/honeypot/b/") for v in a["volumes"]] + [
        "/srv/honeypot/secrets-b:/run/secrets/llm:ro"
    ]
    assert b["container_name"] == "cowrie-b"


def test_cowrie_b_settings(compose):
    env = compose["services"]["cowrie-b"]["environment"]
    assert env["COWRIE_HONEYPOT_SENSOR_NAME"] == "hp-b"
    assert env["COWRIE_HONEYPOT_BACKEND"] == "llm"
    assert env["COWRIE_SSH_LISTEN_ENDPOINTS"] == "tcp:2322:interface=0.0.0.0"
    assert env["COWRIE_LLM_HOST"] == "https://api.tomkaufmann.dev"
    assert env["COWRIE_LLM_PATH"] == "/v1/chat/completions"
    # Prompts und Antworten gehören nicht ins Log.
    assert env["COWRIE_LLM_DEBUG"] == "false"
    # Länger als das Gateway (höchstens 55 s), kürzer als Cowries 60 s für Exec.
    assert 55 < float(env["COWRIE_LLM_REQUEST_TIMEOUT"]) < 60
    assert int(env["COWRIE_LLM_RATE_LIMIT_REQUESTS"]) >= 20
    assert int(env["COWRIE_LLM_RATE_LIMIT_WINDOW"]) == 60


def test_no_secret_and_no_prompt_in_compose(compose):
    env = compose["services"]["cowrie-b"]["environment"]
    for name in ("COWRIE_LLM_API_KEY", "COWRIE_LLM_SYSTEM_PROMPT", "COWRIE_LLM_SYSTEM_PROMPT_EXEC"):
        assert name not in env
    assert "env_file" not in compose["services"]["cowrie-b"]


def test_cowrie_b_is_built_here_and_never_pulled(compose):
    b = compose["services"]["cowrie-b"]
    assert b["build"] == {"context": "./cowrie-b"}
    assert b["pull_policy"] == "build"
    assert b["image"].startswith("localhost/")


def test_vector_reads_b_but_not_its_token(compose):
    mounts = compose["services"]["vector"]["volumes"]
    assert "/srv/honeypot/b/var/log/cowrie:/srv/honeypot/b/var/log/cowrie:ro" in mounts
    assert not any("secrets-b" in mount for mount in mounts)


def test_prepare_host_creates_the_token_directory():
    assert 'cowrie_dir 0700 "$ROOT/secrets-b"' in read(SENSOR / "scripts/prepare-host.sh")


# --- Image ---------------------------------------------------------------------


def test_every_base_image_is_pinned_by_digest():
    froms = re.findall(r"^FROM\s+(\S+)", read(COWRIE_B / "Dockerfile"), flags=re.M)
    assert len(froms) == 3
    for image in froms:
        assert re.fullmatch(r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}", image), image


def test_the_runtime_is_the_image_of_a():
    """method.md 4.1: dasselbe Image plus Patch."""
    froms = re.findall(r"^FROM\s+(\S+)", read(COWRIE_B / "Dockerfile"), flags=re.M)
    assert froms[0] == A_IMAGE
    assert froms[-1] == A_IMAGE


def test_the_build_checks_originals_patch_and_lock():
    dockerfile = read(COWRIE_B / "Dockerfile")
    assert "sha256sum --strict --check upstream.sha256" in dockerfile
    assert "--dry-run --fuzz=0" in dockerfile
    assert "lockcheck.py" in dockerfile


def test_the_patch_touches_only_the_llm_backend():
    patch = read(COWRIE_B / "cowrie-b.patch")
    targets = re.findall(r"^\+\+\+ b/(\S+)", patch, flags=re.M)
    sources = re.findall(r"^--- a/(\S+)", patch, flags=re.M)
    assert targets == sources == ["src/cowrie/llm/llm.py", "src/cowrie/llm/protocol.py"]
    listed = [line.split()[1] for line in read(COWRIE_B / "upstream.sha256").splitlines()]
    assert sorted(listed) == sorted(targets)


def test_the_patch_leaves_the_system_prompt_alone():
    """Die Herkunftsprüfung des Gateways hängt an _build_system_context (E-043)."""
    patch = read(COWRIE_B / "cowrie-b.patch")
    changed = "\n".join(line for line in patch.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---"))
    assert "PROMPT_INJECTION_GUIDANCE" not in changed
    assert "The hostname is" not in changed
    assert "The command to execute is" not in changed


def test_the_lock_is_well_formed():
    locked = lockcheck.read_lock(str(COWRIE_B / "requirements.lock"))
    assert locked
    assert locked["twisted"] == "26.4.0"


def test_lockcheck_names_differences(tmp_path, monkeypatch, capsys):
    lock = tmp_path / "requirements.lock"
    lock.write_text("# Kommentar\nTwisted==26.4.0\nlark==1.3.1\n", encoding="utf-8")
    monkeypatch.setattr(lockcheck, "installed", lambda: {"twisted": "26.4.0", "lark": "1.3.1"})
    assert lockcheck.main([str(lock)]) == 0
    monkeypatch.setattr(lockcheck, "installed", lambda: {"twisted": "26.4.1", "attrs": "26.1.0"})
    assert lockcheck.main([str(lock)]) == 1
    err = capsys.readouterr().err
    assert "lark" in err and "attrs" in err and "26.4.1" in err


# --- Starter -------------------------------------------------------------------

TOKEN = "g" * 64


def files(tmp_path, prompt="You are the bash shell {hostname}.\n  - eingerückt $HOME\n", token=TOKEN + "\n"):
    prompt_path = tmp_path / "prompt.md"
    token_path = tmp_path / "llm_gateway_token"
    prompt_path.write_text(prompt, encoding="utf-8")
    token_path.write_text(token, encoding="ascii")
    return str(prompt_path), str(token_path)


def test_both_prompts_come_from_the_same_file_unchanged(tmp_path):
    prompt_path, token_path = files(tmp_path)
    env = launch.build_environment({"PATH": "/bin"}, prompt_path, token_path)
    prompt = read(Path(prompt_path))
    assert env["COWRIE_LLM_SYSTEM_PROMPT"] == prompt
    assert env["COWRIE_LLM_SYSTEM_PROMPT_EXEC"] == prompt
    assert env["COWRIE_LLM_API_KEY"] == TOKEN
    assert env["PATH"] == "/bin"


def test_the_prompt_from_the_environment_is_replaced(tmp_path):
    prompt_path, token_path = files(tmp_path)
    env = launch.build_environment({"COWRIE_LLM_SYSTEM_PROMPT_EXEC": "fremd"}, prompt_path, token_path)
    assert env["COWRIE_LLM_SYSTEM_PROMPT_EXEC"] == env["COWRIE_LLM_SYSTEM_PROMPT"]


@pytest.mark.parametrize("token", ["", "kurz", "g" * 31, "g" * 40 + " x", "g" * 40 + "\x00"])
def test_without_a_proper_token_it_does_not_start(tmp_path, token):
    prompt_path, token_path = files(tmp_path, token=token)
    with pytest.raises(launch.StartError) as caught:
        launch.build_environment({}, prompt_path, token_path)
    assert token.strip() == "" or token not in str(caught.value)


def test_without_files_it_does_not_start(tmp_path):
    with pytest.raises(launch.StartError):
        launch.build_environment({}, str(tmp_path / "fehlt.md"), str(tmp_path / "fehlt"))
    prompt_path, _ = files(tmp_path)
    with pytest.raises(launch.StartError):
        launch.build_environment({}, prompt_path, str(tmp_path / "fehlt"))


def test_an_empty_prompt_does_not_start(tmp_path):
    prompt_path, token_path = files(tmp_path, prompt="  \n")
    with pytest.raises(launch.StartError):
        launch.build_environment({}, prompt_path, token_path)


def test_the_starter_uses_the_mounted_paths(compose):
    assert launch.PROMPT_PATH == "/cowrie/persona/prompt.md"
    assert any(v.endswith(":/run/secrets/llm:ro") for v in compose["services"]["cowrie-b"]["volumes"])
    assert launch.TOKEN_PATH == "/run/secrets/llm/llm_gateway_token"


# --- Persona und Größe der Anfrage -------------------------------------------------


def test_the_persona_stays_under_the_size_the_gateway_was_checked_for():
    """Mit den längsten Adressen eingesetzt (E-044, Abschnitt Gateway)."""
    prompt = read(SENSOR / "persona/prompt.md")
    rendered = prompt.replace("{ip}", LONGEST_IP).replace("{ip6}", LONGEST_IP6)
    assert len(rendered) <= PERSONA_MAX_CHARS
