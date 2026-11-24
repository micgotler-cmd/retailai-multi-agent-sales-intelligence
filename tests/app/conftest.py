"""Fixtures for the app tests: a run folder written by the real Crew 1 tools (no LLM)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app import common
from src.repositories import run_artifacts as ra
from src.tools import data_tools as dt
from tests.conftest import ITEMS, write_scope_file

TOOL_RUN = "20261124-120000-abc123"


@pytest.fixture
def tool_run(m5_raw_dir: Path, tmp_path: Path, monkeypatch) -> Path:
    """A complete run folder: the tools' real outputs on synthetic M5 data, plus a report.

    The tools are called directly (no agent, no LLM); insights.md is the template.
    """
    runs = tmp_path / "tool-runs"
    run_dir = runs / TOOL_RUN
    run_dir.mkdir(parents=True)
    scope = write_scope_file(tmp_path / "scope.json", ITEMS + ["HOBBIES_1_003"])
    paths = dt.RunPaths(m5_raw_dir, scope, run_dir)
    for tool in (
        dt.ValidateRawDataTool,
        dt.BuildCleanDataTool,
        dt.RunEdaTool,
        dt.WriteContractTool,
    ):
        tool(paths=paths).run()
    shutil.copyfile(paths.out(dt.INSIGHTS_TEMPLATE), paths.out(dt.INSIGHTS))
    report = {
        "run_id": TOOL_RUN,
        "status": "completed",
        "insights_source": "agent",
        "fallback_reason": None,
        "problems": [],
        "llm_budget": {"calls": 8, "max_calls": 100, "tokens": 0, "max_tokens": 200000},
    }
    (run_dir / ra.REPORT_FILE).write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setenv(common.RUNS_DIR_ENV, str(runs))
    return run_dir
