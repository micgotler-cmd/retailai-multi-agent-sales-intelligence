"""Read-only access to the run folders `artifacts/runs/<run_id>/` (P-13 step 1).

The Streamlit pages read crew outputs only through this module, so they never
touch file paths, compute statistics or call an LLM. It lists runs, loads one
run's reports and texts, and says which files are missing or unreadable, so a
page can show a message instead of failing. It never reads `clean_data.csv`:
the screens show aggregates and summaries only, never data rows (T-04). The
planned `LocalRepository` (database-design.md) can wrap these functions.

This module imports no CrewAI code, so the app starts fast; a test checks that
its file names match the Crew 1 runner's.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_RUNS_DIR = Path("artifacts/runs")
REPORT_FILE = "crew1_report.json"
CREW1_FILES = (  # the Crew 1 outputs (M-02 artifacts and their supporting files)
    "quality_report.json",
    "clean_data.csv",
    "cleaning_log.json",
    "eda_report.html",
    "eda_summary.json",
    "insights.md",
    "dataset_contract.json",
    "contract_check.json",
)
NEVER_READ = frozenset({"clean_data.csv"})  # row-level data: presence only (T-04)
FALLBACK_MARKER = "<!-- insights_source: template -->"  # written by the Crew 1 runner
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
RUN_ID_TIME = re.compile(r"^(\d{8}-\d{6})-")


class RunNotFound(Exception):
    """The run id is invalid or has no folder."""


@dataclass(frozen=True)
class RunSummary:
    """One line of the run list."""

    run_id: str
    started_at: datetime | None  # from the run id (UTC), None for other ids
    status: str  # "completed", "failed", "incomplete" (no report) or "unreadable"
    insights_source: str | None  # "agent", "template", "none", or None without a report
    problem_count: int
    llm_calls: int | None
    llm_tokens: int | None


@dataclass
class RunArtifacts:
    """The readable outputs of one run. Missing or unreadable files are listed, not raised."""

    run_id: str
    path: Path
    report: dict | None
    present: dict[str, bool]
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        return [name for name, ok in self.present.items() if not ok]

    def json(self, name: str) -> dict | None:
        """A JSON output, or None if it is missing or unreadable (the reason goes to errors)."""
        text = self.text(name)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self.errors[name] = f"not valid JSON ({exc.msg}, line {exc.lineno})"
            return None
        if not isinstance(data, dict):
            self.errors[name] = "not a JSON object"
            return None
        return data

    def text(self, name: str) -> str | None:
        """A text output, or None if it is missing or unreadable. Never the clean data."""
        if name in NEVER_READ:
            raise ValueError(f"{name} holds data rows; the screens show only aggregates (T-04)")
        path = self.path / name
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self.errors[name] = f"cannot be read ({type(exc).__name__})"
            return None

    def file_path(self, name: str) -> Path | None:
        """Path of an output for a download link, or None if it is missing."""
        path = self.path / name
        return path if path.is_file() else None

    def insights(self) -> tuple[str | None, bool]:
        """insights.md without the internal fallback marker, and whether it is the fallback."""
        text = self.text("insights.md")
        if text is None:
            return None, False
        fallback = text.startswith(FALLBACK_MARKER)
        if fallback:
            text = text[len(FALLBACK_MARKER) :].lstrip("\n")
        return text, fallback


def _run_dir(runs_dir: Path, run_id: str) -> Path:
    """The folder of a run id; refuses ids that could leave the runs folder."""
    if not RUN_ID.match(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")
    path = Path(runs_dir) / run_id
    if not path.is_dir():
        raise RunNotFound(f"No run folder for {run_id!r} in {runs_dir}")
    return path


def _started_at(run_id: str) -> datetime | None:
    m = RUN_ID_TIME.match(run_id)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def _summary(path: Path) -> RunSummary:
    run_id = path.name
    report_path = path / REPORT_FILE
    if not report_path.is_file():
        return RunSummary(run_id, _started_at(run_id), "incomplete", None, 0, None, None)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        budget = report.get("llm_budget") or {}
        return RunSummary(
            run_id,
            _started_at(run_id),
            str(report["status"]),
            report.get("insights_source"),
            len(report.get("problems") or []),
            budget.get("calls"),
            budget.get("tokens"),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, AttributeError):
        return RunSummary(run_id, _started_at(run_id), "unreadable", None, 0, None, None)


def list_runs(runs_dir: Path = DEFAULT_RUNS_DIR) -> list[RunSummary]:
    """All run folders, newest first ([] if the runs folder does not exist yet)."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    folders = [p for p in runs_dir.iterdir() if p.is_dir() and RUN_ID.match(p.name)]
    return sorted((_summary(p) for p in folders), key=lambda r: r.run_id, reverse=True)


def latest_completed(runs: list[RunSummary]) -> RunSummary | None:
    """The newest completed run, the default on every page."""
    return next((r for r in runs if r.status == "completed"), None)


def load_run(run_id: str, runs_dir: Path = DEFAULT_RUNS_DIR) -> RunArtifacts:
    """The outputs of one run. Raises RunNotFound for an unknown or invalid id."""
    path = _run_dir(Path(runs_dir), run_id)
    run = RunArtifacts(run_id, path, None, {n: (path / n).is_file() for n in CREW1_FILES})
    run.report = run.json(REPORT_FILE)
    return run
