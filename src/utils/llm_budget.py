"""Per-run LLM budget: call and token caps (T-01, LLM_MAX_CALLS_PER_RUN, LLM_MAX_TOKENS_PER_RUN).

Uses CrewAI's supported `before_llm_call` hook, which runs before every LLM call
made by an agent and can block it. Once a cap is reached, the next call is
blocked before it reaches OpenAI; CrewAI then raises LLMCallBlockedError and the
crew runner records the run as failed with the reason.

Tokens are the real counts reported by the provider (CrewAI tracks them on the
LLM). The check happens before each call, so the last allowed call can take the
total past the token cap by at most one call (bounded by LLM_MAX_OUTPUT_TOKENS
plus that call's input).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from crewai.hooks import register_before_llm_call_hook, unregister_before_llm_call_hook
from crewai.llms.base_llm import BaseLLM

logger = logging.getLogger(__name__)


def _total_tokens(llm: BaseLLM) -> int:
    return int(llm.get_token_usage_summary().total_tokens or 0)


@dataclass
class LLMBudget:
    """Counts LLM calls and tokens for one run and blocks calls beyond the caps."""

    llm: BaseLLM
    max_calls: int
    max_tokens: int
    calls: int = 0
    stop_reason: str | None = None
    _start_tokens: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.max_tokens < 1:
            raise ValueError("LLM budget caps must be positive")
        self._start_tokens = _total_tokens(self.llm)

    @property
    def tokens(self) -> int:
        """Tokens used by this run so far (provider-reported)."""
        return _total_tokens(self.llm) - self._start_tokens

    def before_call(self, context) -> bool | None:
        """CrewAI hook: return False to block the call, None to allow it.

        Every LLM call during the run counts, whichever LLM object makes it (fail
        safe: one crew runs at a time, so nothing escapes the cap).
        """
        if self.calls >= self.max_calls:
            return self._block(f"LLM call cap reached: {self.calls} of {self.max_calls} calls")
        if self.tokens >= self.max_tokens:
            return self._block(f"LLM token cap reached: {self.tokens} of {self.max_tokens} tokens")
        self.calls += 1
        return None

    def _block(self, reason: str) -> bool:
        if self.stop_reason is None:
            logger.error("%s; stopping the LLM stage (LLM_MAX_*_PER_RUN)", reason)
        self.stop_reason = reason
        return False

    def usage(self) -> dict:
        """Calls and tokens used, the caps, and why the run was stopped (if it was)."""
        return {
            "calls": self.calls,
            "max_calls": self.max_calls,
            "tokens": self.tokens,
            "max_tokens": self.max_tokens,
            "stop_reason": self.stop_reason,
        }


@contextmanager
def enforce_budget(budget: LLMBudget) -> Iterator[LLMBudget]:
    """Register the budget hook for the duration of a run, and always remove it."""
    register_before_llm_call_hook(budget.before_call)
    try:
        yield budget
    finally:
        unregister_before_llm_call_hook(budget.before_call)
