"""Unit tests for the per-run LLM budget (no crew, no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.utils.llm_budget import LLMBudget, enforce_budget
from tests.fake_llm import fake_llm


def context(llm):
    return SimpleNamespace(llm=llm)


def test_allows_calls_up_to_the_cap():
    llm = fake_llm([])
    budget = LLMBudget(llm, max_calls=2, max_tokens=1000)
    assert budget.before_call(context(llm)) is None
    assert budget.before_call(context(llm)) is None
    assert budget.before_call(context(llm)) is False
    assert budget.calls == 2 and "call cap" in budget.stop_reason


def test_token_cap_uses_provider_reported_tokens():
    llm = fake_llm(["a", "b"], tokens_per_call=600)
    budget = LLMBudget(llm, max_calls=10, max_tokens=1000)
    assert budget.before_call(context(llm)) is None
    llm.call("x")  # reports 600 tokens
    assert budget.before_call(context(llm)) is None  # 600 < 1000
    llm.call("y")  # 1,200 tokens
    assert budget.before_call(context(llm)) is False
    assert budget.tokens == 1200 and "token cap" in budget.stop_reason


def test_tokens_count_from_the_start_of_the_run():
    llm = fake_llm(["a", "b"], tokens_per_call=500)
    llm.call("earlier run")
    budget = LLMBudget(llm, max_calls=10, max_tokens=1000)
    assert budget.tokens == 0  # earlier usage of the same LLM object is not counted
    llm.call("this run")
    assert budget.tokens == 500


def test_every_llm_counts_fail_safe():
    budget = LLMBudget(fake_llm([]), max_calls=1, max_tokens=1000)
    assert budget.before_call(context(fake_llm([]))) is None  # another LLM object still counts
    assert budget.before_call(context(object())) is False


@pytest.mark.parametrize(("calls", "tokens"), [(0, 10), (10, 0), (-1, 10)])
def test_caps_must_be_positive(calls, tokens):
    with pytest.raises(ValueError, match="positive"):
        LLMBudget(fake_llm([]), max_calls=calls, max_tokens=tokens)


def test_enforce_budget_registers_and_removes_the_hook():
    from crewai.hooks import get_before_llm_call_hooks

    budget = LLMBudget(fake_llm([]), max_calls=1, max_tokens=10)
    before = len(get_before_llm_call_hooks())
    with pytest.raises(RuntimeError), enforce_budget(budget):
        assert len(get_before_llm_call_hooks()) == before + 1
        raise RuntimeError("crew failed")
    assert len(get_before_llm_call_hooks()) == before


def test_usage_report():
    budget = LLMBudget(fake_llm([]), max_calls=3, max_tokens=100)
    assert budget.usage() == {
        "calls": 0,
        "max_calls": 3,
        "tokens": 0,
        "max_tokens": 100,
        "stop_reason": None,
    }
