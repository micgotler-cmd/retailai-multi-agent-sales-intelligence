"""Crew 1, the Data Analyst Crew: tasks, crew and a thin runner (M-01 to M-03).

Three agents, three sequential tasks: validate -> clean -> analyse. The runner
creates the run folder `artifacts/runs/<run_id>/`, runs the crew, then checks the
outputs deterministically (it does not trust the agents' words). If Agent 3's
insights fail the citation check, the template insights (computed by Python)
are used and the problem is recorded. Gate 1 itself belongs to the Flow (P-10).

Usage (needs a local .env with the OpenAI settings; this calls the OpenAI API):
    uv run python -m src.crews.data_analyst_crew
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from crewai import Crew, Process, Task
from crewai.llms.base_llm import BaseLLM

from src.agents.data_analyst_agents import (
    create_business_analyst,
    create_data_cleaner,
    create_data_validator,
)
from src.data.scope import DEFAULT_SCOPE_PATH
from src.tools import data_tools as dt
from src.utils.llm import disable_crewai_telemetry
from src.utils.llm_budget import LLMBudget, enforce_budget

logger = logging.getLogger(__name__)

REQUIRED_OUTPUTS = [  # M-02 artifacts plus their supporting files
    dt.QUALITY_REPORT,
    dt.CLEAN_DATA,
    dt.CLEANING_LOG,
    dt.EDA_REPORT,
    dt.EDA_SUMMARY,
    dt.INSIGHTS,
    dt.CONTRACT,
    dt.CONTRACT_CHECK,
]
REPORT_FILE = "crew1_report.json"


# --------------------------------------------------------------- definitions


def build_tasks(validator, cleaner, analyst) -> list[Task]:
    """The three tasks, in order; each later task sees the earlier results."""
    validate = Task(
        description=(
            "Call the validate_raw_data tool exactly once. Then report the overall status, "
            "every blocking failure and every warning, in plain language, using only the "
            "tool result."
        ),
        expected_output="A short validation summary: status, failures and warnings.",
        agent=validator,
    )
    clean = Task(
        description=(
            "If validation passed, call the build_clean_data tool exactly once. Summarize what "
            "the cleaning did (rows in and out, rows dropped before first sale, closure days "
            "flagged, missing prices) using only numbers from the tool result. If validation "
            "failed, do not call the tool; say that cleaning was skipped and why."
        ),
        expected_output="A short cleaning summary with the counts from the tool.",
        agent=cleaner,
        context=[validate],
    )
    analyse = Task(
        description=(
            "1. Call run_eda once to get the numbered facts. "
            "2. Call write_dataset_contract once. "
            "3. Write business insights in Markdown for store managers: overall demand, demand "
            "groups and categories (per item), products, calendar patterns, SNAP days and events, "
            "prices, and limitations. Every number must be a fact's 'display' text followed by "
            "its id in brackets, for example '2.31 [F39]'. Use no other numbers. Say that SNAP, "
            "event and price findings are associations, not causal effects, and that price "
            "changes are not promotions. "
            "4. Call save_insights with the Markdown. If it returns problems, fix exactly those "
            "and call it again. Your final answer is the saved insights or the remaining problems."
        ),
        expected_output="The saved Markdown insights, every number cited as '<value> [Fnn]'.",
        agent=analyst,
        context=[validate, clean],
    )
    return [validate, clean, analyse]


def build_crew(llm: BaseLLM, paths: dt.RunPaths) -> Crew:
    """Crew 1 with its three agents, each limited to its own tools."""
    validator = create_data_validator(llm, dt.validator_tools(paths))
    cleaner = create_data_cleaner(llm, dt.cleaner_tools(paths))
    analyst = create_business_analyst(llm, dt.analyst_tools(paths))
    return Crew(
        agents=[validator, cleaner, analyst],
        tasks=build_tasks(validator, cleaner, analyst),
        process=Process.sequential,
        memory=False,
        verbose=False,
    )


# --------------------------------------------------------------------- runner


@dataclass
class Crew1Result:
    """Outcome of one Crew 1 run, also saved as crew1_report.json in the run folder."""

    run_id: str
    run_dir: str
    status: str  # "completed" or "failed"
    insights_source: str  # "agent", "template" or "none"
    problems: list[str] = field(default_factory=list)
    artifacts: dict[str, bool] = field(default_factory=dict)
    token_usage: dict = field(default_factory=dict)
    llm_budget: dict = field(default_factory=dict)
    agent_summaries: list[str] = field(default_factory=list)


def new_run_id() -> str:
    """A sortable, unique run id, for example 20261123-171500-a1b2c3."""
    return f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def check_outputs(paths: dt.RunPaths) -> list[str]:
    """Deterministic check of the run folder after the crew finished."""
    problems = [f"Missing output: {n}" for n in REQUIRED_OUTPUTS if not paths.out(n).is_file()]
    for name in (dt.QUALITY_REPORT, dt.CONTRACT_CHECK):
        path = paths.out(name)
        if path.is_file() and json.loads(path.read_text(encoding="utf-8"))["status"] != "pass":
            problems.append(f"{name} status is not pass")
    return problems


def _use_template_insights(paths: dt.RunPaths, result: Crew1Result) -> None:
    if paths.out(dt.INSIGHTS).is_file():
        result.insights_source = "agent"
    elif paths.out(dt.INSIGHTS_TEMPLATE).is_file():
        shutil.copyfile(paths.out(dt.INSIGHTS_TEMPLATE), paths.out(dt.INSIGHTS))
        result.insights_source = "template"
        result.problems.append(
            "Agent insights were not saved (citation check failed or not attempted); "
            "the deterministic template insights were used"
        )
        logger.warning("Using template insights for run %s", result.run_id)


def run_data_analyst_crew(
    llm: BaseLLM,
    raw_dir: Path = Path("data/raw"),
    scope_path: Path = DEFAULT_SCOPE_PATH,
    runs_dir: Path = Path("artifacts/runs"),
    run_id: str | None = None,
    *,
    max_calls: int,
    max_tokens: int,
) -> Crew1Result:
    """Run Crew 1 into artifacts/runs/<run_id>/ and verify its outputs.

    max_calls and max_tokens are the per-run caps (LLM_MAX_CALLS_PER_RUN,
    LLM_MAX_TOKENS_PER_RUN); they are required, so no run is ever uncapped.
    """
    disable_crewai_telemetry()
    run_id = run_id or new_run_id()
    paths = dt.RunPaths(Path(raw_dir), Path(scope_path), Path(runs_dir) / run_id)
    paths.run_dir.mkdir(parents=True, exist_ok=True)  # the CLI may have created it for the log
    used = [n for n in [*REQUIRED_OUTPUTS, REPORT_FILE] if paths.out(n).exists()]
    if used:
        raise FileExistsError(f"Run folder {paths.run_dir} already has outputs: {used}")
    result = Crew1Result(run_id, str(paths.run_dir), "failed", "none")
    budget = LLMBudget(llm, max_calls=max_calls, max_tokens=max_tokens)
    logger.info("Crew 1 run %s started (caps: %d calls, %d tokens)", run_id, max_calls, max_tokens)
    try:
        with enforce_budget(budget):
            output = build_crew(llm, paths).kickoff()
        result.agent_summaries = [t.raw for t in output.tasks_output]
        result.token_usage = output.token_usage.model_dump() if output.token_usage else {}
    except Exception as exc:  # the crew must fail cleanly, never crash the caller
        logger.exception("Crew 1 run %s raised an error", run_id)
        result.problems.append(f"Crew error: {type(exc).__name__}: {exc}")
    result.llm_budget = budget.usage()
    if budget.stop_reason:
        result.problems.append(f"Stopped by the LLM budget: {budget.stop_reason}")

    _use_template_insights(paths, result)
    result.problems.extend(check_outputs(paths))
    result.artifacts = {n: paths.out(n).is_file() for n in REQUIRED_OUTPUTS}
    blocking = [p for p in result.problems if not p.startswith("Agent insights")]
    result.status = "failed" if blocking else "completed"
    paths.out(REPORT_FILE).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    logger.info("Crew 1 run %s: %s (insights: %s)", run_id, result.status, result.insights_source)
    return result


def main(argv: list[str] | None = None) -> int:
    """Run Crew 1 with the configured OpenAI model. Calls the OpenAI API (costs money)."""
    import argparse

    from src.utils.config import (
        ConfigError,
        load_llm_settings,
        load_settings,
        read_env,
        secret_values,
    )
    from src.utils.llm import build_llm
    from src.utils.logging_setup import setup_from_env, setup_logging

    parser = argparse.ArgumentParser(description="Run Crew 1 (Data Analyst Crew).")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--runs-dir", type=Path, default=Path("artifacts/runs"))
    args = parser.parse_args(argv)
    setup_from_env()
    try:
        env = read_env()
        llm_settings = load_llm_settings(env)
        llm = build_llm(llm_settings)
        level = load_settings(env).log_level
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1
    run_id = new_run_id()
    setup_logging(level, args.runs_dir / run_id / "crew1.log", secret_values(env))
    result = run_data_analyst_crew(
        llm,
        args.raw_dir,
        args.scope,
        args.runs_dir,
        run_id,
        max_calls=llm_settings.max_calls_per_run,
        max_tokens=llm_settings.max_tokens_per_run,
    )
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
