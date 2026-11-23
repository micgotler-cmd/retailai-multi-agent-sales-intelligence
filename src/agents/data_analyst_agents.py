"""Agent definitions for Crew 1, the Data Analyst Crew (M-01 to M-03). Definitions only.

Each agent gets only its own tools (src/tools/data_tools.py). Agents decide which
tool to call, read the JSON results and explain them; they never compute numbers
or edit data (CLAUDE.md). Delegation is off and iterations are capped to bound
LLM calls and cost (T-01).
"""

from __future__ import annotations

from crewai import Agent
from crewai.llms.base_llm import BaseLLM
from crewai.tools import BaseTool

MAX_ITER = 4  # LLM steps per agent; each tool call is one step (T-01 cost control)
ANALYST_MAX_ITER = 7  # EDA, contract, save insights (with one retry) and the final answer

NO_INVENTED_NUMBERS = (
    "You never calculate, estimate or change numbers yourself. Every number you report "
    "comes from a tool result."
)


def _agent(
    role: str,
    goal: str,
    backstory: str,
    llm: BaseLLM,
    tools: list[BaseTool],
    max_iter: int = MAX_ITER,
) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=f"{backstory} {NO_INVENTED_NUMBERS}",
        tools=tools,
        llm=llm,
        max_iter=max_iter,
        allow_delegation=False,
        memory=False,
        verbose=False,
    )


def create_data_validator(llm: BaseLLM, tools: list[BaseTool]) -> Agent:
    """Agent 1: checks the raw M5 files before anything else runs."""
    return _agent(
        role="Data Validator",
        goal="Confirm the raw M5 files are complete and valid for the approved scope, and "
        "report every blocking failure and warning clearly.",
        backstory="You are a careful data quality analyst for a retail forecasting project. "
        "You run the validation tool and explain its findings in plain business language.",
        llm=llm,
        tools=tools,
    )


def create_data_cleaner(llm: BaseLLM, tools: list[BaseTool]) -> Agent:
    """Agent 2: reshapes and cleans the data with the approved rules (T-13)."""
    return _agent(
        role="Data Cleaner",
        goal="Produce clean_data.csv with the approved cleaning rules and document every "
        "cleaning action with its counts.",
        backstory="You are a data engineer who documents every change to the data. The "
        "cleaning rules are fixed (T-13); you run the cleaning tool and explain what it did.",
        llm=llm,
        tools=tools,
    )


def create_business_analyst(llm: BaseLLM, tools: list[BaseTool]) -> Agent:
    """Agent 3: EDA, evidence-based insights and the dataset contract."""
    return _agent(
        role="Business Analyst",
        goal="Turn the EDA facts into clear, evidence-based business insights and write the "
        "dataset contract for the Data Scientist Crew.",
        backstory="You are a retail business analyst. You explain demand patterns to managers "
        "using only the numbered EDA facts, cite every number with its fact id, and describe "
        "SNAP, event and price findings as associations, never as causes.",
        llm=llm,
        tools=tools,
        max_iter=ANALYST_MAX_ITER,
    )
