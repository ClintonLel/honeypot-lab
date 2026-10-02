"""Tests für den Patch an Cowries LLM-Backend (Schritt 7.3, E-041, E-044).

Laufen mit ``twisted.trial`` im gebauten Image von cowrie-b, gegen die
gepatchten Dateien und ein Fake-Gateway im selben Prozess
(``fake_gateway.py``). Aufruf in der CI siehe ``.github/workflows/ci.yml``,
Job ``cowrie-b``.

Geprüft wird, was die Auswertung braucht (method.md V1, V2, V4):
``cowrie.command.input`` für Exec, je Befehl genau ein ``cowrie.llm.response``
mit Index, Ausgang, Status, Antwortzeit und Länge, ohne Text, und die motd.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

from twisted.internet import defer, reactor, task
from twisted.trial import unittest

from cowrie.core.rate_limiter import RateLimiter
from cowrie.llm import llm as llm_module
from cowrie.llm import protocol as llm_protocol
from cowrie.test.fake_transport import FakeTransport

import fake_gateway

HOSTNAME = "bld-ci-03"
OUR_FIELDS = {
    "command_index",
    "outcome",
    "http_status",
    "latency_ms",
    "output_chars",
    "client_gone",
    "input_sha256",
}
PROXY_VARIABLES = ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY")


def avatar() -> SimpleNamespace:
    return SimpleNamespace(environ={}, server=SimpleNamespace(hostname=HOSTNAME), username="root")


def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def events_of(transport: FakeTransport, eventid: str) -> list[dict[str, Any]]:
    return [e for e in transport.dispatchedEvents if e["eventid"] == eventid]


@defer.inlineCallbacks
def until(predicate, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Bedingung nicht rechtzeitig erfüllt")
        yield task.deferLater(reactor, 0.01, lambda: None)


def free_port() -> int:
    """Ein Port, auf dem sicher niemand lauscht."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class PatchTestCase(unittest.TestCase):
    """Fake-Gateway, frischer LLM-Client und großzügiges Limit je Test."""

    def setUp(self) -> None:
        self.gateway, self.listening = fake_gateway.start()
        self.addCleanup(self.listening.stopListening)
        self.addCleanup(self.gateway.stop)

        self.environ: dict[str, str | None] = {}
        motd_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(motd_dir, "etc"))
        self.motd = b"bld-ci-03 - CI build worker\n\nAuthorized use only.\n"
        with open(os.path.join(motd_dir, "etc", "motd"), "wb") as motd:
            motd.write(self.motd)
        self.setenv("COWRIE_HONEYPOT_CONTENTS_PATH", motd_dir)
        self.setenv("COWRIE_HONEYPOT_INTERNET_FACING_IP", "192.0.2.10")
        self.setenv("COWRIE_HONEYPOT_INTERNET_FACING_IPV6", "2001:db8::10")
        self.setenv("COWRIE_LLM_API_KEY", "test-token")
        self.point_at(self.listening.getHost().port)
        for name in PROXY_VARIABLES:
            self.setenv(name, None)

        self.limiter = RateLimiter(max_requests=1000, window_seconds=60)
        self.patch(llm_protocol, "llm_rate_limiter", self.limiter)

    def setenv(self, name: str, value: str | None) -> None:
        if name not in self.environ:
            self.environ[name] = os.environ.get(name)
            self.addCleanup(self._restore, name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def _restore(self, name: str) -> None:
        old = self.environ[name]
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old

    def point_at(self, port: int) -> None:
        """Neuer gemeinsamer Client gegen diesen Port."""
        self.setenv("COWRIE_LLM_HOST", f"http://127.0.0.1:{port}")
        self.setenv("COWRIE_LLM_PATH", "/v1/chat/completions")
        llm_module.reset_shared_client()
        self.client = llm_module.get_shared_client()
        self.client.request_timeout = 0
        self.addCleanup(self.client._conn_pool.closeCachedConnections)

    # --- Sitzungen ---------------------------------------------------------------

    def exec_channel(self, command: bytes, transport: FakeTransport | None = None):
        transport = transport or FakeTransport("", "31337")
        ended: list[Any] = []
        transport.transport.processEnded = ended.append
        proto = llm_protocol.HoneyPotExecProtocol(avatar(), command)
        proto.makeConnection(transport)
        self.addCleanup(proto.setTimeout, None)
        return proto, transport, ended

    def interactive(self):
        transport = FakeTransport("", "31337")
        proto = llm_protocol.HoneyPotInteractiveProtocol(avatar())
        proto.makeConnection(transport)
        self.addCleanup(proto.setTimeout, None)
        return proto, transport

    def assert_clean(self, response: dict[str, Any], command_input: dict[str, Any]) -> None:
        """Genau unsere Felder, kein Text aus Befehl oder Antwort."""
        identity = set(command_input) - {"input"}
        self.assertEqual(set(response) - identity, OUR_FIELDS)
        dumped = json.dumps(response)
        self.assertNotIn(fake_gateway.ANSWER, dumped)
        command = command_input["input"]
        self.assertNotIn(command, [value for value in response.values() if isinstance(value, str)])
        # Kurze Befehle wie "id" stecken zufällig in Schlüsseln wie "session".
        if len(command) >= 8:
            self.assertNotIn(command, dumped)


class ClassifyTests(unittest.TestCase):
    def test_status_codes_map_to_outcomes(self) -> None:
        expected = {
            200: "ok",
            429: "rate_limited",
            502: "upstream_error",
            503: "unavailable",
            504: "timeout",
            0: "error",
            400: "error",
            401: "error",
            413: "error",
            500: "error",
        }
        for status, outcome in expected.items():
            self.assertEqual(llm_module.classify_status(status), outcome, status)

    def test_a_call_without_answer_has_no_status(self) -> None:
        call = llm_module.LLMCall()
        self.assertEqual((call.outcome, call.http_status, call.latency_ms), ("error", None, None))


class ExecTests(PatchTestCase):
    @defer.inlineCallbacks
    def run_exec(self, command: str):
        proto, transport, ended = self.exec_channel(command.encode())
        yield until(lambda: ended)
        inputs = events_of(transport, "cowrie.command.input")
        responses = events_of(transport, "cowrie.llm.response")
        self.assertEqual([e["input"] for e in inputs], [command])
        self.assertEqual(len(responses), 1)
        self.assertLess(
            transport.dispatchedEvents.index(inputs[0]), transport.dispatchedEvents.index(responses[0])
        )
        self.assertEqual(ended[0].value.exitCode, 0)
        response = responses[0]
        self.assertEqual(response["command_index"], 1)
        self.assertEqual(response["input_sha256"], digest(command))
        self.assertFalse(response["client_gone"])
        self.assert_clean(response, inputs[0])
        return response, transport.value()

    @defer.inlineCallbacks
    def test_ok(self):
        response, output = yield self.run_exec("uname -a")
        self.assertEqual(
            (response["outcome"], response["http_status"], response["output_chars"]),
            ("ok", 200, len(fake_gateway.ANSWER)),
        )
        self.assertIsInstance(response["latency_ms"], int)
        self.assertEqual(output, fake_gateway.ANSWER.encode() + b"\n")

    @defer.inlineCallbacks
    def test_an_empty_answer_is_ok_with_nothing_shown(self):
        response, output = yield self.run_exec("lab-empty")
        self.assertEqual((response["outcome"], response["http_status"], response["output_chars"]), ("ok", 200, 0))
        self.assertEqual(output, b"")

    @defer.inlineCallbacks
    def test_http_errors(self):
        for status, outcome in (
            (429, "rate_limited"),
            (502, "upstream_error"),
            (503, "unavailable"),
            (504, "timeout"),
            (500, "error"),
            (400, "error"),
            (401, "error"),
        ):
            response, output = yield self.run_exec(f"lab-status-{status}")
            self.assertEqual(
                (response["outcome"], response["http_status"], response["output_chars"]),
                (outcome, status, 0),
                status,
            )
            self.assertIsInstance(response["latency_ms"], int)
            # Wie ohne Patch: keine Ausgabe, Exit 0.
            self.assertEqual(output, b"")

    @defer.inlineCallbacks
    def test_a_200_without_json_is_an_error_with_its_status(self):
        response, output = yield self.run_exec("lab-bad")
        self.assertEqual((response["outcome"], response["http_status"]), ("error", 200))
        self.assertEqual(output, b"")
        # Cowrie loggt den Fehler selbst, wie ohne Patch.
        self.assertEqual(len(self.flushLoggedErrors(json.JSONDecodeError)), 1)

    @defer.inlineCallbacks
    def test_a_dropped_connection_has_no_status(self):
        response, output = yield self.run_exec("lab-close")
        self.assertEqual((response["outcome"], response["http_status"]), ("error", None))
        self.assertIsInstance(response["latency_ms"], int)
        self.assertEqual(output, b"")

    @defer.inlineCallbacks
    def test_a_closed_port_has_no_status_and_no_output(self):
        """Verbindungsfehler: Status 0 statt 500, beim Client wie ohne Patch nichts."""
        self.point_at(free_port())
        response, output = yield self.run_exec("uname -a")
        self.assertEqual((response["outcome"], response["http_status"]), ("error", None))
        self.assertEqual(output, b"")

    @defer.inlineCallbacks
    def test_our_own_timeout(self):
        self.client.request_timeout = 0.3
        response, output = yield self.run_exec("lab-sleep-3")
        self.assertEqual((response["outcome"], response["http_status"]), ("timeout", None))
        self.assertGreaterEqual(response["latency_ms"], 300)
        self.assertLess(response["latency_ms"], 3000)
        self.assertEqual(output, b"")

    @defer.inlineCallbacks
    def test_without_timeout_a_slow_answer_still_arrives(self):
        response, _ = yield self.run_exec("lab-sleep-0.5")
        self.assertEqual(response["outcome"], "ok")
        self.assertGreaterEqual(response["latency_ms"], 500)

    @defer.inlineCallbacks
    def test_the_whole_command_is_logged_even_when_it_is_cut_for_the_prompt(self):
        command = "echo " + "A" * 8187
        response, _ = yield self.run_exec(command)
        self.assertEqual(response["outcome"], "ok")
        # Ans Gateway gingen nur max_command_length Zeichen.
        self.assertEqual(self.gateway.commands, [command[: llm_protocol.MAX_COMMAND_LENGTH]])

    @defer.inlineCallbacks
    def test_an_empty_exec_is_logged_and_sent(self):
        response, _ = yield self.run_exec("")
        self.assertEqual(response["outcome"], "ok")
        self.assertEqual(response["input_sha256"], digest(""))

    @defer.inlineCallbacks
    def test_a_multi_line_command_is_one_command(self):
        response, _ = yield self.run_exec("uname -a\nid; whoami")
        self.assertEqual(response["command_index"], 1)

    @defer.inlineCallbacks
    def test_the_local_limit_logs_the_command_and_skips_the_gateway(self):
        """V1: auch ein begrenzter Exec-Befehl erscheint als command.input."""
        self.patch(llm_protocol, "llm_rate_limiter", RateLimiter(max_requests=1, window_seconds=60))
        first, _ = yield self.run_exec("id")
        second, output = yield self.run_exec("uname -a")
        self.assertEqual(first["outcome"], "ok")
        self.assertEqual(
            (second["outcome"], second["http_status"], second["latency_ms"], second["output_chars"]),
            ("local_rate_limit", None, None, 0),
        )
        self.assertEqual(self.gateway.commands, ["id"])
        self.assertEqual(output, b"")

    @defer.inlineCallbacks
    def test_a_client_that_left_is_marked(self):
        proto, transport, ended = self.exec_channel(b"lab-sleep-0.3")
        proto.connectionLost("weg")
        yield until(lambda: events_of(transport, "cowrie.llm.response"))
        response = events_of(transport, "cowrie.llm.response")[0]
        self.assertEqual((response["outcome"], response["client_gone"]), ("ok", True))
        self.assertEqual(response["output_chars"], len(fake_gateway.ANSWER))

    @defer.inlineCallbacks
    def test_eof_right_after_the_command_still_gets_the_answer(self):
        """Wie A: Ein EOF des Clients beendet den Befehl nicht vor der Antwort (E-044)."""
        proto, transport, ended = self.exec_channel(b"lab-sleep-0.3")
        proto.eofReceived()
        self.assertEqual(ended, [])
        yield until(lambda: ended)
        self.assertEqual(len(ended), 1)
        self.assertEqual(ended[0].value.exitCode, 0)
        self.assertEqual(transport.value(), fake_gateway.ANSWER.encode() + b"\n")
        response = events_of(transport, "cowrie.llm.response")[0]
        self.assertEqual((response["outcome"], response["client_gone"]), ("ok", False))

    @defer.inlineCallbacks
    def test_eof_after_the_answer_ends_as_before(self):
        proto, transport, ended = self.exec_channel(b"id")
        yield until(lambda: ended)
        proto.eofReceived()
        self.assertEqual(len(ended), 2)

    @defer.inlineCallbacks
    def test_eof_on_a_limited_command_ends_at_once(self):
        self.patch(llm_protocol, "llm_rate_limiter", RateLimiter(max_requests=0, window_seconds=60))
        proto, transport, ended = self.exec_channel(b"id")
        self.assertEqual(len(ended), 1)
        self.assertFalse(proto.llm_pending)
        yield until(lambda: events_of(transport, "cowrie.llm.response"))

    @defer.inlineCallbacks
    def test_parallel_channels_keep_their_numbers(self):
        """Zwei Exec-Kanäle einer Verbindung, der zweite antwortet zuerst."""
        first_transport = FakeTransport("", "31337")
        second_transport = FakeTransport("", "31337")
        second_transport.transport.session.conn.transport = first_transport.transport.session.conn.transport
        _, _, first_ended = self.exec_channel(b"lab-sleep-0.5", first_transport)
        _, _, second_ended = self.exec_channel(b"id", second_transport)
        yield until(lambda: first_ended and second_ended)

        inputs = events_of(first_transport, "cowrie.command.input")
        responses = events_of(first_transport, "cowrie.llm.response")
        self.assertEqual([e["input"] for e in inputs], ["lab-sleep-0.5", "id"])
        self.assertEqual([r["command_index"] for r in responses], [2, 1])
        by_index = {r["command_index"]: r["input_sha256"] for r in responses}
        self.assertEqual(by_index, {1: digest("lab-sleep-0.5"), 2: digest("id")})

    @defer.inlineCallbacks
    def test_get_response_still_works_without_a_call_object(self):
        text = yield self.client.get_response(["system prompt The command to execute is: id"])
        self.assertEqual(text, fake_gateway.ANSWER)


class InteractiveTests(PatchTestCase):
    def test_the_motd_comes_first_and_no_welcome(self):
        _, transport = self.interactive()
        output = transport.value()
        self.assertTrue(output.startswith(self.motd), output[:80])
        self.assertNotIn(b"Welcome to", output)
        self.assertTrue(output.endswith(f"root@{HOSTNAME}:/# ".encode()))

    def test_without_a_motd_nothing_is_shown(self):
        self.setenv("COWRIE_HONEYPOT_CONTENTS_PATH", tempfile.mkdtemp())
        _, transport = self.interactive()
        self.assertTrue(transport.value().endswith(f"root@{HOSTNAME}:/# ".encode()))
        self.assertNotIn(b"Welcome to", transport.value())

    @defer.inlineCallbacks
    def test_every_line_gets_one_response_with_its_number(self):
        proto, transport = self.interactive()
        lines = ["uname -a", "", "lab-status-503", "id"]
        for line in lines:
            proto.lineReceived(line.encode())
        yield until(lambda: len(events_of(transport, "cowrie.llm.response")) == len(lines))

        inputs = events_of(transport, "cowrie.command.input")
        responses = sorted(events_of(transport, "cowrie.llm.response"), key=lambda r: r["command_index"])
        self.assertEqual([e["input"] for e in inputs], lines)
        self.assertEqual([r["command_index"] for r in responses], [1, 2, 3, 4])
        self.assertEqual([r["input_sha256"] for r in responses], [digest(line) for line in lines])
        self.assertEqual([r["outcome"] for r in responses], ["ok", "ok", "unavailable", "ok"])
        for response in responses:
            self.assert_clean(response, inputs[0])

    @defer.inlineCallbacks
    def test_the_local_limit_in_an_interactive_session(self):
        self.patch(llm_protocol, "llm_rate_limiter", RateLimiter(max_requests=1, window_seconds=60))
        proto, transport = self.interactive()
        proto.lineReceived(b"id")
        proto.lineReceived(b"uname -a")
        yield until(lambda: len(events_of(transport, "cowrie.llm.response")) == 2)
        responses = sorted(events_of(transport, "cowrie.llm.response"), key=lambda r: r["command_index"])
        self.assertEqual([r["outcome"] for r in responses], ["ok", "local_rate_limit"])
        self.assertEqual(len(events_of(transport, "cowrie.command.input")), 2)


class SystemContextTests(PatchTestCase):
    """Der Patch darf den System-Prompt nicht ändern (E-043, Herkunftsprüfung)."""

    TEMPLATE = "Persona of {hostname} at {ip} and {ip6}.\n"

    def expected(self, exec_command: str = "") -> str:
        context = self.TEMPLATE.format(hostname=HOSTNAME, ip="192.0.2.10", ip6="2001:db8::10")
        context += llm_protocol.PROMPT_INJECTION_GUIDANCE
        context += f" The hostname is '{HOSTNAME}' and username is 'root'. The current working directory is '/'."
        if exec_command:
            context += f" The command to execute is: {exec_command}"
        return context

    def test_interactive_and_exec_prompts_keep_their_form(self):
        self.setenv("COWRIE_LLM_SYSTEM_PROMPT", self.TEMPLATE)
        self.setenv("COWRIE_LLM_SYSTEM_PROMPT_EXEC", self.TEMPLATE)
        proto, _ = self.interactive()
        self.assertEqual(proto._build_system_context(), self.expected())
        self.assertEqual(proto._build_system_context(exec_command="id"), self.expected("id"))
