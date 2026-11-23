"""CrewAI tools for Crew 1 (Data Analyst). Thin wrappers; all logic lives in src/data.

Each tool is created for one run with fixed paths (RunPaths), so an agent can
never choose which files are read or written. Tools return short JSON summaries:
counts, statuses and EDA facts, never data rows (T-04 condition 6). A tool whose
prerequisite is missing (for example cleaning before a passed validation)
raises ToolRefused, which CrewAI reports back to the agent; the crew runner then
checks the outputs deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.data import cleaning, contract, eda, etl, validation
from src.data.insights_check import check_insights, display_values
from src.data.scope import load_scope

QUALITY_REPORT = "quality_report.json"
CLEAN_DATA = "clean_data.csv"
CLEANING_LOG = "cleaning_log.json"
EDA_SUMMARY = "eda_summary.json"
EDA_REPORT = "eda_report.html"
INSIGHTS_TEMPLATE = "insights_template.md"
INSIGHTS = "insights.md"
CONTRACT = "dataset_contract.json"
CONTRACT_CHECK = "contract_check.json"


class ToolRefused(Exception):
    """A tool cannot run because a prerequisite of the run is missing or failed."""


@dataclass(frozen=True)
class RunPaths:
    """Inputs and the run folder of one Crew 1 run."""

    raw_dir: Path
    scope_path: Path
    run_dir: Path

    def out(self, name: str) -> Path:
        """Path of an output file in the run folder."""
        return self.run_dir / name


def _json(data: dict) -> str:
    """Compact JSON (fewer tokens for the LLM)."""
    return json.dumps(data, separators=(",", ":"), default=str)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(paths: RunPaths, *names: str) -> None:
    missing = [n for n in names if not paths.out(n).is_file()]
    if missing:
        raise ToolRefused(
            f"Missing earlier output(s): {', '.join(missing)}. Run the earlier step first."
        )


class _RunTool(BaseTool):
    """Base for tools bound to one run's paths."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    paths: RunPaths


# ------------------------------------------------------------------- Agent 1


class ValidateRawDataTool(_RunTool):
    name: str = "validate_raw_data"
    description: str = (
        "Validate the raw M5 files for the approved scope. Takes no input. Writes "
        "quality_report.json and returns the overall status, blocking failures and warnings."
    )

    def _run(self, **_: Any) -> str:
        scope = load_scope(self.paths.scope_path)
        report = validation.run_validation(self.paths.raw_dir, scope)
        validation.write_quality_report(report, self.paths.out(QUALITY_REPORT))
        return _json(
            {
                "status": report["status"],
                "summary": report["summary"],
                "warnings": [
                    {"check": c["name"], "message": c["message"]}
                    for c in report["checks"]
                    if c["status"] == validation.WARN
                ],
                "failures": [
                    {"check": c["name"], "message": c["message"]}
                    for c in report["checks"]
                    if c["status"] == validation.FAIL
                ],
            }
        )


# ------------------------------------------------------------------- Agent 2


class BuildCleanDataTool(_RunTool):
    name: str = "build_clean_data"
    description: str = (
        "Reshape and clean the data with the approved rules (T-13). Takes no input. Runs only "
        "after validation passed. Writes clean_data.csv and cleaning_log.json and returns counts."
    )

    def _run(self, **_: Any) -> str:
        _require(self.paths, QUALITY_REPORT)
        if _read_json(self.paths.out(QUALITY_REPORT))["status"] != validation.PASS:
            raise ToolRefused("Validation did not pass; the data must not be cleaned.")
        scope = load_scope(self.paths.scope_path)
        clean, log = cleaning.clean(etl.build_long_table(self.paths.raw_dir, scope), scope)
        cleaning.write_outputs(clean, log, self.paths.run_dir)
        actions = {a["action"]: a for a in log["actions"]}
        return _json(
            {
                "rows_in": log["rows_in"],
                "rows_out": log["rows_out"],
                "items": log["items"],
                "first_date": log["first_date"],
                "last_date": log["last_date"],
                "pre_launch_rows_dropped": actions["drop_rows_before_first_sale"]["rows_dropped"],
                "closure_rows_flagged": actions["flag_store_closed"]["rows_flagged"],
                "closure_dates": actions["flag_store_closed"]["dates"],
                "missing_prices": actions["check_prices"]["missing_prices"],
                "rules": [a["rule"] for a in log["actions"]],
            }
        )


# ------------------------------------------------------------------- Agent 3


class RunEdaTool(_RunTool):
    name: str = "run_eda"
    description: str = (
        "Run the exploratory data analysis on the training period. Takes no input. Writes "
        "eda_report.html and eda_summary.json and returns the numbered facts. Each fact has an "
        "id (e.g. F39) and a 'display' text; use exactly that text when citing the fact."
    )

    def _run(self, **_: Any) -> str:
        _require(self.paths, CLEAN_DATA)
        scope = load_scope(self.paths.scope_path)
        result = eda.run_eda(eda.load_clean(self.paths.out(CLEAN_DATA)), scope)
        self.paths.out(EDA_SUMMARY).write_text(json.dumps(result.summary, indent=2), "utf-8")
        self.paths.out(EDA_REPORT).write_text(result.html, encoding="utf-8")
        self.paths.out(INSIGHTS_TEMPLATE).write_text(result.insights, encoding="utf-8")
        shown = display_values(result.summary["facts"])
        return _json(
            {
                "period": result.summary["period"],
                "rules": result.summary["rules"],
                "facts": [
                    {
                        "id": f["id"],
                        "topic": f["topic"],
                        "metric": f["metric"],
                        "display": shown[f["id"]],
                        "unit": f["unit"],
                        "keys": f["keys"],
                        "definition": f["definition"],
                    }
                    for f in result.summary["facts"]
                ],
            }
        )


class WriteContractTool(_RunTool):
    name: str = "write_dataset_contract"
    description: str = (
        "Write dataset_contract.json for the clean data and check the data against it. Takes "
        "no input. Returns the contract check status and the rules checked."
    )

    def _run(self, **_: Any) -> str:
        _require(self.paths, CLEAN_DATA, CLEANING_LOG)
        scope = load_scope(self.paths.scope_path)
        clean = pd.read_csv(self.paths.out(CLEAN_DATA))
        log = _read_json(self.paths.out(CLEANING_LOG))
        built = contract.build_contract(clean, scope, log, self.paths.raw_dir)
        contract.write_json(built, self.paths.out(CONTRACT))
        report = contract.contract_report(contract.check_against_contract(clean, built))
        contract.write_json(report, self.paths.out(CONTRACT_CHECK))
        return _json(
            {
                "status": report["status"],
                "failed_rules": report["failed_rules"],
                "rules": [c["name"] for c in report["checks"]],
            }
        )


class SaveInsightsInput(BaseModel):
    """Input of save_insights."""

    markdown: str = Field(..., description="The full insights text in Markdown")


class SaveInsightsTool(_RunTool):
    name: str = "save_insights"
    description: str = (
        "Save the business insights (Markdown) as insights.md. Every number must be a fact's "
        "display text followed by its id in brackets, e.g. '2.31 [F39]'; no other numbers. "
        "Returns 'saved' or the list of problems to fix."
    )
    args_schema: type[BaseModel] = SaveInsightsInput

    def _run(self, markdown: str, **_: Any) -> str:
        _require(self.paths, EDA_SUMMARY)
        facts = _read_json(self.paths.out(EDA_SUMMARY))["facts"]
        problems = check_insights(markdown, facts)
        if problems:
            return _json({"saved": False, "problems": problems})
        self.paths.out(INSIGHTS).write_text(markdown.strip() + "\n", encoding="utf-8")
        return _json({"saved": True})


def validator_tools(paths: RunPaths) -> list[BaseTool]:
    """Tools of Agent 1, the Data Validator."""
    return [ValidateRawDataTool(paths=paths)]


def cleaner_tools(paths: RunPaths) -> list[BaseTool]:
    """Tools of Agent 2, the Data Cleaner."""
    return [BuildCleanDataTool(paths=paths)]


def analyst_tools(paths: RunPaths) -> list[BaseTool]:
    """Tools of Agent 3, the Business Analyst."""
    return [RunEdaTool(paths=paths), WriteContractTool(paths=paths), SaveInsightsTool(paths=paths)]
