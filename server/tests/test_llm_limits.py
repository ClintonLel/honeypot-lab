"""Kosten, usage, Budget und Minutengrenze des LLM-Gateways (app/llm_limits.py)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.llm_limits import (
    INT4_MAX,
    Budget,
    CallWindow,
    Prices,
    Usage,
    cost_micros,
    day_start,
    estimate_micros,
    month_start,
    parse_usage,
)

PRICES = Prices(input=Decimal("0.40"), cached_input=Decimal("0.10"), output=Decimal("1.60"))
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


# --- usage -------------------------------------------------------------------


def test_openai_usage_with_cached_tokens():
    usage = parse_usage(
        {
            "usage": {
                "prompt_tokens": 8000,
                "completion_tokens": 120,
                "total_tokens": 8120,
                "prompt_tokens_details": {"cached_tokens": 7424, "audio_tokens": 0},
            }
        }
    )
    assert usage == Usage(prompt_tokens=8000, completion_tokens=120, total_tokens=8120, cached_tokens=7424)


def test_cache_hits_in_the_other_common_form():
    usage = parse_usage(
        {"usage": {"prompt_tokens": 100, "completion_tokens": 5, "prompt_cache_hit_tokens": 64}}
    )
    assert usage == Usage(prompt_tokens=100, completion_tokens=5, total_tokens=105, cached_tokens=64)


def test_usage_without_cache_details_counts_nothing_as_cached():
    usage = parse_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
    assert usage is not None and usage.cached_tokens == 0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"usage": None},
        {"usage": {"completion_tokens": 3}},
        {"usage": {"prompt_tokens": "10", "completion_tokens": 3}},
        {"usage": {"prompt_tokens": -1, "completion_tokens": 3}},
        {"usage": {"prompt_tokens": True, "completion_tokens": 3}},
    ],
)
def test_missing_or_broken_usage_is_none(payload):
    assert parse_usage(payload) is None


def test_absurd_numbers_are_capped_for_the_database():
    usage = parse_usage(
        {
            "usage": {
                "prompt_tokens": 10**12,
                "completion_tokens": 10**12,
                "prompt_tokens_details": {"cached_tokens": 10**13},
            }
        }
    )
    assert usage.prompt_tokens == usage.completion_tokens == usage.total_tokens == INT4_MAX
    assert usage.cached_tokens == usage.prompt_tokens


# --- Kosten ------------------------------------------------------------------


def test_cached_tokens_are_charged_at_the_cache_price():
    usage = Usage(prompt_tokens=8000, completion_tokens=120, total_tokens=8120, cached_tokens=7424)
    # 576 × 0,40 + 7.424 × 0,10 + 120 × 1,60 = 230,4 + 742,4 + 192 = 1.164,8 µ€
    assert cost_micros(usage, PRICES) == 1165


def test_without_cache_everything_is_charged_at_the_input_price():
    usage = Usage(prompt_tokens=8000, completion_tokens=120, total_tokens=8120)
    assert cost_micros(usage, PRICES) == 3_200 + 192


def test_costs_are_rounded_up():
    assert cost_micros(Usage(prompt_tokens=1), PRICES) == 1


def test_one_million_tokens_cost_the_price_per_million():
    assert cost_micros(Usage(prompt_tokens=1_000_000), PRICES) == 400_000  # 0,40 €


def test_the_estimate_is_an_upper_bound():
    # 30.000 Zeichen → 10.000 Tokens ohne Cache, dazu die volle Ausgabe:
    # 4.000 + 3.276,8 µ€, aufgerundet.
    assert estimate_micros(30_000, 2048, PRICES) == 7_277
    realistic = cost_micros(Usage(prompt_tokens=7_500, completion_tokens=300, cached_tokens=7_000), PRICES)
    assert estimate_micros(30_000, 2048, PRICES) > realistic


# --- Budget ------------------------------------------------------------------


def loaded_budget(month: int = 0, day: int = 0, *, month_limit: int = 1_000, day_limit: int = 100) -> Budget:
    budget = Budget(month_limit, day_limit)
    seen = {}

    async def read(since_month, since_day):
        seen["month"], seen["day"] = since_month, since_day
        return month, day

    asyncio.run(budget.load(read, NOW))
    assert seen == {"month": month_start(NOW), "day": day_start(NOW)}
    return budget


def test_period_starts_are_utc():
    berlin = timezone(timedelta(hours=2))
    late = datetime(2026, 11, 1, 1, 30, tzinfo=berlin)  # in UTC noch der 31.10.
    assert month_start(late) == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert day_start(late) == datetime(2026, 10, 31, tzinfo=timezone.utc)


def test_the_budget_is_loaded_from_the_ledger_once():
    calls = []

    async def read(since_month, since_day):
        calls.append(1)
        await asyncio.sleep(0.01)
        return 5, 3

    async def main():
        budget = Budget(100, 10)
        await asyncio.gather(*(budget.load(read, NOW) for _ in range(5)))
        return budget

    budget = asyncio.run(main())
    assert calls == [1]
    assert (budget.spent_month, budget.spent_day) == (5, 3)


def test_a_failed_load_leaves_the_budget_unloaded():
    async def read(since_month, since_day):
        raise ConnectionError("db weg")

    budget = Budget(100, 10)
    with pytest.raises(ConnectionError):
        asyncio.run(budget.load(read, NOW))
    assert budget.loaded is False


def test_reaching_the_day_or_month_limit_stops():
    assert loaded_budget(day=99).exceeded(NOW) is False
    assert loaded_budget(day=100).exceeded(NOW) is True
    assert loaded_budget(month=1_000).exceeded(NOW) is True


def test_costs_count_immediately():
    budget = loaded_budget(day=90)
    budget.add(10, NOW, NOW)
    assert (budget.spent_month, budget.spent_day) == (10, 100)
    assert budget.exceeded(NOW) is True


def test_a_new_day_starts_at_zero_and_keeps_the_month():
    budget = loaded_budget(month=500, day=100)
    tomorrow = NOW + timedelta(days=1)
    assert budget.exceeded(tomorrow) is False
    assert (budget.spent_month, budget.spent_day) == (500, 0)


def test_a_new_month_starts_at_zero():
    budget = loaded_budget(month=1_000, day=100)
    november = datetime(2026, 11, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert budget.exceeded(november) is False
    assert (budget.spent_month, budget.spent_day) == (0, 0)


def test_a_request_across_midnight_counts_for_the_day_it_started():
    budget = loaded_budget()
    started = datetime(2026, 10, 14, 23, 59, 50, tzinfo=timezone.utc)
    finished = datetime(2026, 10, 15, 0, 0, 20, tzinfo=timezone.utc)
    budget.add(40, started, finished)
    assert (budget.spent_month, budget.spent_day) == (40, 0)


def test_a_request_across_the_month_boundary_does_not_count_for_the_new_month():
    budget = loaded_budget()
    started = datetime(2026, 10, 31, 23, 59, 50, tzinfo=timezone.utc)
    finished = datetime(2026, 11, 1, 0, 0, 20, tzinfo=timezone.utc)
    budget.add(40, started, finished)
    assert (budget.spent_month, budget.spent_day) == (0, 0)


# --- Minutengrenze -----------------------------------------------------------


def test_the_window_lets_through_exactly_the_limit():
    window = CallWindow(per_minute=3)
    assert [window.acquire(t) for t in (0.0, 1.0, 2.0)] == [0.0, 0.0, 0.0]
    assert window.acquire(3.0) == pytest.approx(57.0)


def test_refused_calls_do_not_count():
    window = CallWindow(per_minute=1)
    window.acquire(0.0)
    for t in (10.0, 20.0, 30.0):
        assert window.acquire(t) > 0
    assert window.acquire(60.0) == 0.0


def test_the_window_slides():
    window = CallWindow(per_minute=2)
    window.acquire(0.0)
    window.acquire(30.0)
    assert window.acquire(59.9) > 0
    assert window.acquire(60.0) == 0.0
    assert window.acquire(61.0) > 0
