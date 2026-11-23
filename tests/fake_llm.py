"""A scripted fake LLM for CrewAI tests: no network, no key, no cost.

Responses follow CrewAI's text (ReAct) format, so real agents call real tools:
    "Thought: ...\nAction: <tool>\nAction Input: {...}"  -> CrewAI runs the tool
    "Thought: ...\nFinal Answer: ..."                     -> the task ends
A response may be a callable that receives the messages, for answers that
depend on earlier tool results.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from crewai.llms.base_llm import BaseLLM
from pydantic import Field

Response = str | Callable[[Any], str]


def action(tool: str, **tool_input: Any) -> str:
    """A ReAct step that calls a tool."""
    return f"Thought: I will use {tool}.\nAction: {tool}\nAction Input: {json.dumps(tool_input)}"


def final(answer: str) -> str:
    """A ReAct step that ends the task."""
    return f"Thought: I now know the final answer\nFinal Answer: {answer}"


class FakeLLM(BaseLLM):
    """Returns the scripted responses in order and records every call."""

    responses: list[Any] = Field(default_factory=list)
    calls: list[Any] = Field(default_factory=list)
    tokens_per_call: int = 0  # reported like provider usage, for token-cap tests

    def call(
        self,
        messages,
        tools=None,
        callbacks=None,
        available_functions=None,
        from_task=None,
        from_agent=None,
        response_model=None,
        **kwargs,
    ) -> str:
        self.calls.append(messages)
        if self.tokens_per_call:
            prompt = self.tokens_per_call * 7 // 10
            self._track_token_usage_internal(
                {
                    "prompt_tokens": prompt,
                    "completion_tokens": self.tokens_per_call - prompt,
                    "total_tokens": self.tokens_per_call,
                }
            )
        if not self.responses:
            raise RuntimeError("FakeLLM has no scripted response left")
        response = self.responses.pop(0)
        return response(messages) if callable(response) else response

    def supports_function_calling(self) -> bool:
        return False


def fake_llm(responses: list[Response], tokens_per_call: int = 0) -> FakeLLM:
    """A new FakeLLM with its own response list and call log."""
    return FakeLLM(
        model="fake-model", responses=list(responses), calls=[], tokens_per_call=tokens_per_call
    )
