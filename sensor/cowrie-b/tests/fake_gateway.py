"""Attrappe des LLM-Gateways für die Tests von cowrie-b (Schritt 7.3).

Antwortet wie das echte Gateway (server/app/llm_gateway.py) im OpenAI-Format.
Was es tut, hängt am Befehl: bei Exec am Ende des System-Prompts, interaktiv
an der letzten Nachricht.

    lab-status-NNN   HTTP NNN mit Fehlerrumpf wie das Gateway
    lab-empty        200 mit leerem content
    lab-bad          200 mit einem Rumpf, der kein JSON ist
    lab-close        Verbindung schließen, ohne zu antworten
    lab-sleep-S      S Sekunden warten, dann 200
    alles andere     200 mit festem Text

Im Prozess (Trial-Tests) über ``start()``, eigenständig für den Paritätstest
der CI mit ``python3 fake_gateway.py --port 18080``. Nur Standardbibliothek
und Twisted, beides steckt im Image von Cowrie.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from twisted.internet import reactor
from twisted.web import resource, server

ANSWER = "Linux bld-ci-03 6.12.107+deb13-amd64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux"
EXEC_MARK = " The command to execute is: "

# Wie _ERRORS im Gateway, gekürzt auf das, was Cowrie liest: nichts.
ERRORS = {
    400: "invalid_request",
    401: "invalid_token",
    413: "request_too_large",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "unavailable",
    504: "upstream_timeout",
}


def command_of(body: dict[str, Any]) -> str:
    """Der Befehl, so wie Cowrie ihn geschickt hat."""
    messages = body.get("messages") or []
    if len(messages) > 1:
        return str(messages[-1].get("content", ""))
    system = str(messages[0].get("content", "")) if messages else ""
    cut = system.rfind(EXEC_MARK)
    return system[cut + len(EXEC_MARK) :] if cut >= 0 else ""


def completion(content: str) -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
        }
    ).encode()


class Gateway(resource.Resource):
    isLeaf = True

    def __init__(self) -> None:
        super().__init__()
        # Je Anfrage der Befehl, für Prüfungen in den Tests.
        self.commands: list[str] = []
        # Verzögerte Antworten, damit Tests sie am Ende abräumen können.
        self.pending: list[Any] = []

    def stop(self) -> None:
        for call in self.pending:
            if call.active():
                call.cancel()

    def render_POST(self, request: server.Request) -> bytes | int:
        body = json.loads(request.content.read() or b"{}")
        command = command_of(body)
        self.commands.append(command)
        request.setHeader(b"content-type", b"application/json")

        if command.startswith("lab-status-"):
            status = int(command.removeprefix("lab-status-"))
            request.setResponseCode(status)
            code = ERRORS.get(status, "error")
            return json.dumps({"error": {"message": "x", "type": "server_error", "param": None, "code": code}}).encode()
        if command == "lab-empty":
            return completion("")
        if command == "lab-bad":
            return b"kein json"
        if command == "lab-close":
            request.channel.transport.abortConnection()
            return server.NOT_DONE_YET
        if command.startswith("lab-sleep-"):
            seconds = float(command.removeprefix("lab-sleep-"))

            def finish() -> None:
                if not request.finished and not request._disconnected:
                    request.write(completion(ANSWER))
                    request.finish()

            self.pending.append(reactor.callLater(seconds, finish))
            return server.NOT_DONE_YET
        return completion(ANSWER)


def start(port: int = 0, interface: str = "127.0.0.1") -> tuple[Gateway, Any]:
    """Startet die Attrappe im laufenden Reactor; gibt sie und den Port zurück."""
    gateway = Gateway()
    site = server.Site(gateway)
    site.noisy = False
    listening = reactor.listenTCP(port, site, interface=interface)
    return gateway, listening


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--interface", default="127.0.0.1")
    args = parser.parse_args()
    start(args.port, args.interface)
    reactor.run()


if __name__ == "__main__":
    main()
