"""Testsitzungen gegen Cowrie, nur mit Zählern und Hashes als Ergebnis (7.3).

Ein kleiner SSH-Client auf Twisted Conch, das im Image von Cowrie steckt.
Ihn nutzen das Prüfskript auf dem Sensor (``sensor/scripts/check-cowrie-b.py``)
und der Paritätstest der CI. Er kann, was OpenSSH nur über Umwege kann: einen
leeren Exec-Befehl, zwei parallele Exec-Kanäle auf einer Verbindung, stdin
mit EOF und eine interaktive Sitzung mit pty.

Der Plan kommt als JSON auf stdin, das Ergebnis als JSON auf stdout. Die
Ausgabe der Shell steht nie im Ergebnis, nur ihre Länge und ihr SHA-256:
Modellantworten gehören nicht ins Terminal (method.md 9.7, E-042).

Plan, eine Liste von Sitzungen, jede auf einer eigenen Verbindung:

    [{"name": "exec", "exec": ["uname -a"]},
     {"name": "parallel", "exec": ["uname -a", "id"]},
     {"name": "eof", "exec": ["uname -a"], "eof": true},
     {"name": "stdin", "exec": ["sh"], "stdin": "id\\n"},
     {"name": "shell", "shell": ["uname -a", "", "id"]}]

Aufruf: ``python3 sshdrive.py --host 127.0.0.1 --port 2322 < plan.json``
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import struct
import sys
import time
from hashlib import sha256
from typing import Any

from twisted.conch.ssh import channel, common, connection, session, transport, userauth
from twisted.internet import defer, protocol, reactor, task

# Prompt am Ende der Ausgabe: "root@bld-ci-03:/# " (B) oder ":~# " (A).
PROMPT = re.compile(rb"[#$] $")
# Steuerfolgen des Terminals, etwa "\x1b[4h" für den Einfügemodus.
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
CTRL_D = b"\x04"


def normalized(data: bytes) -> bytes:
    return ANSI.sub(b"", data).replace(b"\r\n", b"\n")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


async def sleep(seconds: float) -> None:
    await task.deferLater(reactor, seconds, lambda: None)


async def until(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            return False
        await sleep(0.05)
    return True


class Channel(channel.SSHChannel):
    name = b"session"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.output = bytearray()
        self.exit_status: int | None = None
        self.opened: defer.Deferred[None] = defer.Deferred()
        self.done = False

    def channelOpen(self, specificData: bytes) -> None:
        self.opened.callback(None)

    def openFailed(self, reason: Any) -> None:
        self.done = True
        self.opened.errback(Exception("Kanal abgelehnt"))

    def dataReceived(self, data: bytes) -> None:
        self.output += data

    def request_exit_status(self, data: bytes) -> int:
        (self.exit_status,) = struct.unpack(">L", data[:4])
        return 1

    def closed(self) -> None:
        self.done = True


class Connection(connection.SSHConnection):
    def __init__(self, ready: defer.Deferred) -> None:
        super().__init__()
        self.ready = ready

    def serviceStarted(self) -> None:
        self.ready.callback(self)


class Auth(userauth.SSHUserAuthClient):
    preferredOrder = [b"password"]

    def __init__(self, user: str, password: str, conn: Connection) -> None:
        super().__init__(user.encode(), conn)
        self.password = password
        self.tries = 0

    def getPassword(self, prompt: Any = None) -> Any:
        self.tries += 1
        # Nur ein Versuch: Ein zweiter heißt, das Passwort wurde abgelehnt.
        return defer.succeed(self.password.encode()) if self.tries == 1 else None

    def getPublicKey(self) -> Any:
        return None


class Transport(transport.SSHClientTransport):
    def verifyHostKey(self, hostKey: bytes, fingerprint: str) -> Any:
        # Der Honeypot-Key ist bewusst nicht bekannt (sensor/README.md).
        return defer.succeed(True)

    def connectionSecure(self) -> None:
        self.requestService(Auth(self.factory.user, self.factory.password, Connection(self.factory.ready)))

    def connectionLost(self, reason: Any) -> None:
        super().connectionLost(reason)
        if not self.factory.ready.called:
            self.factory.ready.errback(Exception("Verbindung verloren"))


class Factory(protocol.ClientFactory):
    protocol = Transport

    def __init__(self, user: str, password: str) -> None:
        self.user = user
        self.password = password
        self.ready: defer.Deferred[Connection] = defer.Deferred()

    def clientConnectionFailed(self, connector: Any, reason: Any) -> None:
        if not self.ready.called:
            self.ready.errback(Exception("keine Verbindung"))


def channel_result(chan: Channel, data: bytes) -> dict[str, Any]:
    return {"exit": chan.exit_status, "bytes": len(data), "sha256": digest(normalized(data))}


async def run_exec(conn: Connection, step: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Alle Befehle gleichzeitig, je ein Kanal auf derselben Verbindung."""
    channels = []
    for command in step["exec"]:
        chan = Channel(conn=conn)
        conn.openChannel(chan)
        channels.append((chan, command))
    for chan, command in channels:
        await chan.opened
        conn.sendRequest(chan, b"exec", common.NS(command.encode()), wantReply=False)
        if "stdin" in step:
            chan.write(step["stdin"].encode())
        # EOF nach dem Befehl, wie ssh mit geschlossenem stdin oder Gos
        # x/crypto/ssh ohne Stdin. Mit stdin immer.
        if step.get("eof", "stdin" in step):
            conn.sendEOF(chan)
    finished = await until(lambda: all(chan.done for chan, _ in channels), timeout)
    return {
        "fertig": finished,
        "kanaele": [channel_result(chan, bytes(chan.output)) for chan, _ in channels],
    }


async def run_shell(conn: Connection, step: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Interaktiv mit pty: nach jeder Zeile auf den nächsten Prompt warten."""
    chan = Channel(conn=conn)
    conn.openChannel(chan)
    await chan.opened
    conn.sendRequest(chan, b"pty-req", session.packRequest_pty_req(b"xterm", (24, 80, 0, 0), b""), wantReply=False)
    conn.sendRequest(chan, b"shell", b"", wantReply=False)

    prompts = 0
    if await until(lambda: PROMPT.search(chan.output) is not None, timeout):
        prompts = 1
    first = bytes(chan.output)
    # Alles vor der Zeile mit dem ersten Prompt ist die motd.
    motd = normalized(first[: first.rfind(b"\n") + 1]) if prompts else b""

    for line in step["shell"]:
        start = len(chan.output)
        chan.write(line.encode() + b"\r")
        if await until(lambda: PROMPT.search(chan.output[start:]) is not None, timeout):
            prompts += 1
    chan.write(CTRL_D)
    finished = await until(lambda: chan.done, 10)
    after = bytes(chan.output)[len(first) :]
    return {
        "fertig": finished,
        "prompts": prompts,
        "motd_sha256": digest(motd),
        "motd_bytes": len(motd),
        "kanaele": [channel_result(chan, after)],
    }


async def run_step(host: str, port: int, user: str, password: str, step: dict[str, Any], timeout: float) -> dict[str, Any]:
    factory = Factory(user, password)
    connector = reactor.connectTCP(host, port, factory, timeout=10)
    result: dict[str, Any] = {"name": step.get("name", ""), "verbunden": False, "fehler": None}
    try:
        conn = await factory.ready
        result["verbunden"] = True
        if "shell" in step:
            result.update(await run_shell(conn, step, timeout))
        else:
            result.update(await run_exec(conn, step, timeout))
    except Exception as exc:  # noqa: BLE001 - nur der Typ, nie Inhalt
        result["fehler"] = type(exc).__name__
    finally:
        connector.disconnect()
        # Cowrie schreibt session.closed erst, wenn die Verbindung weg ist.
        await sleep(0.5)
    return result


async def run_plan(args: argparse.Namespace, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Zufällig je Lauf. Nie "root", nie 123456 (sensor/cowrie/userdb.txt).
    password = "lab-" + secrets.token_hex(8)
    results = []
    for step in plan:
        results.append(await run_step(args.host, args.port, args.user, password, step, args.timeout))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2322)
    parser.add_argument("--user", default="root")
    parser.add_argument("--timeout", type=float, default=70.0, help="Sekunden je Warten auf Antwort")
    args = parser.parse_args()
    plan = json.load(sys.stdin)

    outcome: dict[str, Any] = {}

    def done(results: list[dict[str, Any]]) -> None:
        outcome["results"] = results

    def failed(err: Any) -> None:
        outcome["error"] = err.type.__name__

    d = defer.ensureDeferred(run_plan(args, plan))
    d.addCallbacks(done, failed)
    d.addBoth(lambda _: reactor.stop())
    reactor.run()
    if "error" in outcome:
        print(json.dumps({"fehler": outcome["error"]}))
        raise SystemExit(1)
    print(json.dumps(outcome["results"]))


if __name__ == "__main__":
    main()
