"""Der Anbieter Gemini: Modelle, Preise, Nachrichten, Antworten (app/llm_provider.py, E-045)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.llm_limits import Prices
from app.llm_provider import GEMINI_URL, MODELS, read_reply, to_gemini
from app.llm_request import parse_request
from tests.cowrie_llm import encode, exec_request, interactive_request, system_context
from tests.llm_fakes import completion

# --- Modelle und Preise --------------------------------------------------------


def test_the_url_is_the_openai_compatible_endpoint_without_a_key():
    assert GEMINI_URL == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert "?" not in GEMINI_URL and "key" not in GEMINI_URL


@pytest.mark.parametrize("model", list(MODELS))
def test_only_fixed_model_versions_are_allowed(model):
    """Wie bei Image-Tags: kein Alias, keine Vorschau, die sich ändern kann."""
    assert model.startswith("gemini-")
    assert "latest" not in model and "preview" not in model and "exp" not in model


def test_the_chosen_model_has_the_prices_from_the_price_page():
    """https://ai.google.dev/gemini-api/docs/pricing, Stand 2026-10-01."""
    prices = MODELS["gemini-3.1-flash-lite"].prices_on(date(2026, 10, 14))
    assert prices == Prices(input=Decimal("0.25"), cached_input=Decimal("0.025"), output=Decimal("1.50"))
    assert MODELS["gemini-3.1-flash-lite"].efforts == {"minimal", "low"}


def test_flash_prices_double_on_new_year():
    model = MODELS["gemini-3.8-flash"]
    assert model.prices_on(date(2026, 12, 31)).output == Decimal("3.75")
    assert model.prices_on(date(2027, 1, 1)).output == Decimal("7.50")
    assert model.efforts == {"low"}


# --- Nachrichten ----------------------------------------------------------------


def checked(body):
    return parse_request(encode(body))


def test_exec_becomes_system_plus_user():
    assert to_gemini(checked(exec_request("uname -a"))) == [
        {"role": "system", "content": system_context()},
        {"role": "user", "content": "uname -a"},
    ]


def test_the_command_is_sent_exactly_once():
    command = "echo unverwechselbar-7c1e"
    sent = to_gemini(checked(exec_request(command)))
    assert sum(m["content"].count("unverwechselbar-7c1e") for m in sent) == 1


@pytest.mark.parametrize(
    "body",
    [
        exec_request(""),
        exec_request("   "),
        interactive_request(["User: "]),
        interactive_request(["User: ls", "System: bin", "User: \t"]),
    ],
)
def test_empty_input_is_answered_locally(body):
    assert to_gemini(checked(body)) is None


def test_no_message_with_empty_text_reaches_gemini():
    sent = to_gemini(checked(interactive_request(["User: ", "System: ", "User: cd /tmp", "System:  ", "User: ls"])))
    assert sent[1:] == [{"role": "user", "content": "cd /tmp"}, {"role": "user", "content": "ls"}]


def test_merging_joins_turns_of_the_same_role():
    body = interactive_request(["User: a", "System: x", "User: b", "User: c", "System: y", "System: z", "User: d"])
    assert to_gemini(checked(body), merge_turns=True)[1:] == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "x"},
        {"role": "user", "content": "b\nc"},
        {"role": "assistant", "content": "y\nz"},
        {"role": "user", "content": "d"},
    ]


def test_merging_leaves_alternating_turns_alone():
    body = interactive_request(["User: a", "System: x", "User: b"])
    assert to_gemini(checked(body), merge_turns=True) == to_gemini(checked(body))


def test_the_original_messages_are_not_changed():
    request = checked(interactive_request(["User: a", "User: b"]))
    before = [dict(m) for m in request.messages]
    to_gemini(request, merge_turns=True)
    assert request.messages == before


# --- Antworten ------------------------------------------------------------------


def test_a_normal_answer():
    reply = read_reply(completion("Linux"))
    assert (reply.status, reply.content, reply.finish_reason, reply.block) == ("ok", "Linux", "stop", None)


def test_length_is_passed_on_and_other_reasons_become_stop():
    assert read_reply(completion("x", finish_reason="length")).finish_reason == "length"
    other = read_reply(completion("x", finish_reason="tool_calls"))
    assert (other.finish_reason, other.finish_log) == ("stop", "sonst")


@pytest.mark.parametrize(
    ("finish", "block"),
    [
        ("content_filter", "sonst"),
        ("content_filter: SAFETY", "safety"),
        ("content_filter: RECITATION", "recitation"),
        ("CONTENT_FILTER:spii", "spii"),
        ("content_filter: <script>", "sonst"),
    ],
)
def test_a_filtered_answer_is_blocked(finish, block):
    reply = read_reply(completion("halbe Antwort", finish_reason=finish))
    assert (reply.status, reply.block, reply.content) == ("upstream_blocked", block, "")


def test_no_candidate_means_a_blocked_prompt():
    body = completion()
    body["choices"] = []
    assert (read_reply(body).status, read_reply(body).block) == ("upstream_blocked", "prompt")


@pytest.mark.parametrize("key", ["prompt_feedback", "promptFeedback"])
def test_prompt_feedback_with_a_reason_means_blocked(key):
    body = completion()
    body[key] = {"block_reason": "OTHER"} if key == "prompt_feedback" else {"blockReason": "SAFETY"}
    assert read_reply(body).status == "upstream_blocked"


def test_prompt_feedback_without_a_reason_is_fine():
    body = completion()
    body["prompt_feedback"] = {"safety_ratings": []}
    assert read_reply(body).status == "ok"


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"choices": None}, {"choices": ["x"]}, {"choices": [{"message": "x"}]}, completion(["teil"])],
)
def test_broken_answers_are_errors(payload):
    assert read_reply(payload).status == "upstream_error"
