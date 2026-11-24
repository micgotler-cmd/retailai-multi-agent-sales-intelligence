"""Tests for the Crew 1 tools and the insights citation check (synthetic data, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.tools import data_tools as dt
from tests.conftest import ITEMS, write_scope_file

TOOL_ITEMS = ITEMS + ["HOBBIES_1_003"]


@pytest.fixture
def paths(m5_raw_dir: Path, tmp_path: Path) -> dt.RunPaths:
    scope = write_scope_file(tmp_path / "scope.json", TOOL_ITEMS)
    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True)
    return dt.RunPaths(m5_raw_dir, scope, run_dir)


def run(tool_cls, paths, **kwargs) -> dict:
    return json.loads(tool_cls(paths=paths).run(**kwargs))


def run_all(paths) -> dict:
    run(dt.ValidateRawDataTool, paths)
    run(dt.BuildCleanDataTool, paths)
    return run(dt.RunEdaTool, paths)


# --------------------------------------------------------------------- tools


def test_validate_tool(paths):
    out = run(dt.ValidateRawDataTool, paths)
    assert out["status"] == "pass" and out["failures"] == []
    assert paths.out(dt.QUALITY_REPORT).is_file()


def test_clean_tool_returns_counts_not_rows(paths):
    run(dt.ValidateRawDataTool, paths)
    out = run(dt.BuildCleanDataTool, paths)
    clean = pd.read_csv(paths.out(dt.CLEAN_DATA))
    assert out["rows_out"] == len(clean) and out["missing_prices"] == 0
    assert out["pre_launch_rows_dropped"] == 121  # HOBBIES_1_003: 120 days, HOBBIES_1_001: 1 day
    assert "units_sold" not in json.dumps(out)  # no data rows go to the LLM


def test_eda_tool_returns_facts_with_display_text(paths):
    out = run_all(paths)
    assert out["period"]["name"] == "training"
    first = out["facts"][0]
    assert {"id", "display", "unit", "definition"} <= set(first)
    for name in (dt.EDA_SUMMARY, dt.EDA_REPORT, dt.INSIGHTS_TEMPLATE):
        assert paths.out(name).is_file()


def test_contract_tool(paths):
    run_all(paths)
    out = run(dt.WriteContractTool, paths)
    assert out["status"] == "pass" and out["failed_rules"] == []
    assert paths.out(dt.CONTRACT).is_file() and paths.out(dt.CONTRACT_CHECK).is_file()


def test_save_insights_accepts_cited_text(paths):
    run_all(paths)
    template = paths.out(dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    assert run(dt.SaveInsightsTool, paths, markdown=template) == {"saved": True}
    assert paths.out(dt.INSIGHTS).is_file()


def test_save_insights_rejects_invented_numbers(paths):
    run_all(paths)
    text = paths.out(dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    bad = text + "\n- Sales will grow 15% next year.\n"
    out = run(dt.SaveInsightsTool, paths, markdown=bad)
    assert out["saved"] is False and any("15%" in p for p in out["problems"])
    assert not paths.out(dt.INSIGHTS).exists()


# ------------------------------------------------------------- prerequisites


def test_clean_refused_without_validation(paths):
    with pytest.raises(dt.ToolRefused, match="quality_report.json"):
        dt.BuildCleanDataTool(paths=paths)._run()


def test_clean_refused_when_validation_failed(paths):
    cal = pd.read_csv(paths.raw_dir / "calendar.csv")
    cal.drop(index=[30]).to_csv(paths.raw_dir / "calendar.csv", index=False)
    assert run(dt.ValidateRawDataTool, paths)["status"] == "fail"
    with pytest.raises(dt.ToolRefused, match="did not pass"):
        dt.BuildCleanDataTool(paths=paths)._run()
    assert not paths.out(dt.CLEAN_DATA).exists()


@pytest.mark.parametrize(
    ("tool", "missing"),
    [
        (dt.RunEdaTool, "clean_data.csv"),
        (dt.WriteContractTool, "clean_data.csv"),
        (dt.SaveInsightsTool, "eda_summary.json"),
    ],
)
def test_tools_refuse_without_earlier_outputs(paths, tool, missing):
    kwargs = {"markdown": "x"} if tool is dt.SaveInsightsTool else {}
    with pytest.raises(dt.ToolRefused, match=missing):
        tool(paths=paths)._run(**kwargs)


def test_tool_sets_per_agent(paths):
    assert [t.name for t in dt.validator_tools(paths)] == ["validate_raw_data"]
    assert [t.name for t in dt.cleaner_tools(paths)] == ["build_clean_data"]
    assert [t.name for t in dt.analyst_tools(paths)] == [
        "run_eda",
        "write_dataset_contract",
        "save_insights",
    ]


# ------------------------------------------------------- save_insights retries

BAD = "# Insights\n\nSales will grow 15% next year, not causal."


def test_save_insights_caps_the_problems_shown(paths):
    run_all(paths)
    many = BAD + "".join(f"\n- Item {i}0 sold." for i in range(1, 20))
    out = run(dt.SaveInsightsTool, paths, markdown=many)
    assert out["problem_count"] > dt.MAX_PROBLEMS_SHOWN
    assert len(out["problems"]) == dt.MAX_PROBLEMS_SHOWN
    assert out["more_problems_not_shown"] == out["problem_count"] - dt.MAX_PROBLEMS_SHOWN
    assert out["attempts_left"] == dt.MAX_SAVE_ATTEMPTS - 1
    attempts = dt.read_insights_attempts(paths)  # the full list is kept for the report
    assert len(attempts[0]["problems"]) == out["problem_count"]


def test_save_insights_stops_after_the_attempt_limit(paths):
    run_all(paths)
    for _ in range(dt.MAX_SAVE_ATTEMPTS):
        assert run(dt.SaveInsightsTool, paths, markdown=BAD)["saved"] is False
    template = paths.out(dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    out = run(dt.SaveInsightsTool, paths, markdown=template)  # valid, but too late
    assert out["saved"] is False and out["attempts_left"] == 0
    assert not paths.out(dt.INSIGHTS).exists()
    assert len(dt.read_insights_attempts(paths)) == dt.MAX_SAVE_ATTEMPTS


def test_save_insights_records_a_successful_retry(paths):
    run_all(paths)
    run(dt.SaveInsightsTool, paths, markdown=BAD)
    template = paths.out(dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    assert run(dt.SaveInsightsTool, paths, markdown=template) == {"saved": True}
    assert [a["saved"] for a in dt.read_insights_attempts(paths)] == [False, True]
