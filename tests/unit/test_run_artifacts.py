"""Tests for the read-only run folder reader used by the Streamlit pages (P-13 step 1)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.repositories import run_artifacts as ra

DONE = "20261124-164623-7d1d1d"
FAILED = "20261123-175149-8df956"
EMPTY = "20261125-090000-aaaaaa"


def report(status="completed", source="agent", problems=(), calls=10, tokens=44069) -> dict:
    budget = {"calls": calls, "max_calls": 100, "tokens": tokens, "max_tokens": 200000}
    return {
        "run_id": "x",
        "status": status,
        "insights_source": source,
        "problems": list(problems),
        "llm_budget": budget,
    }


def make_run(runs: Path, run_id: str, rep: dict | None = None, files=ra.CREW1_FILES) -> Path:
    path = runs / run_id
    path.mkdir(parents=True)
    for name in files:
        content = "{}" if name.endswith(".json") else "x"
        (path / name).write_text(content, encoding="utf-8")
    if rep is not None:
        (path / ra.REPORT_FILE).write_text(json.dumps(rep), encoding="utf-8")
    return path


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    make_run(runs, DONE, report())
    make_run(runs, FAILED, report("failed", "template", ["Missing output: x"], 3, 900))
    make_run(runs, EMPTY, None, files=())  # started, no report yet
    (runs / "notes.txt").write_text("not a run", encoding="utf-8")
    return runs


# ------------------------------------------------------------------ run list


def test_list_runs_newest_first_with_status(runs):
    listed = ra.list_runs(runs)
    assert [r.run_id for r in listed] == [EMPTY, DONE, FAILED]
    empty, done, failed = listed
    assert (empty.status, empty.insights_source, empty.llm_calls) == ("incomplete", None, None)
    assert (done.status, done.insights_source, done.llm_calls, done.llm_tokens) == (
        "completed",
        "agent",
        10,
        44069,
    )
    assert (failed.status, failed.problem_count) == ("failed", 1)
    assert done.started_at == datetime(2026, 11, 24, 16, 46, 23)


def test_latest_completed_skips_unfinished_runs(runs):
    assert ra.latest_completed(ra.list_runs(runs)).run_id == DONE
    assert ra.latest_completed([]) is None


def test_no_runs_folder_gives_an_empty_list(tmp_path):
    assert ra.list_runs(tmp_path / "missing") == []


def test_unreadable_report_is_listed_not_raised(runs):
    (runs / DONE / ra.REPORT_FILE).write_text("{broken", encoding="utf-8")
    done = next(r for r in ra.list_runs(runs) if r.run_id == DONE)
    assert done.status == "unreadable"


def test_other_run_ids_have_no_start_time(tmp_path):
    make_run(tmp_path, "test-run", report())
    assert ra.list_runs(tmp_path)[0].started_at is None


# ------------------------------------------------------------------ one run


def test_load_run_reports_present_and_missing_files(runs):
    (runs / DONE / "insights.md").unlink()
    run = ra.load_run(DONE, runs)
    assert run.report["status"] == "completed"
    assert run.missing == ["insights.md"]
    assert run.json("quality_report.json") == {}
    assert run.json("insights.md") is None and run.text("insights.md") is None
    assert run.file_path("eda_report.html") == runs / DONE / "eda_report.html"
    assert run.file_path("insights.md") is None


def test_invalid_json_is_an_error_not_an_exception(runs):
    (runs / DONE / "quality_report.json").write_text("[1, 2", encoding="utf-8")
    (runs / DONE / "cleaning_log.json").write_text("[1, 2]", encoding="utf-8")
    run = ra.load_run(DONE, runs)
    assert run.json("quality_report.json") is None
    assert run.json("cleaning_log.json") is None
    assert "not valid JSON" in run.errors["quality_report.json"]
    assert run.errors["cleaning_log.json"] == "not a JSON object"


def test_run_without_report(runs):
    run = ra.load_run(EMPTY, runs)
    assert run.report is None and run.missing == list(ra.CREW1_FILES)


def test_clean_data_rows_are_never_read(runs):
    """T-04: the screens show aggregates only; the reader refuses to read the data rows."""
    run = ra.load_run(DONE, runs)
    assert run.present["clean_data.csv"] is True
    with pytest.raises(ValueError, match="aggregates"):
        run.text("clean_data.csv")
    with pytest.raises(ValueError):
        run.json("clean_data.csv")


@pytest.mark.parametrize("bad", ["../secrets", "..", "a/b", "a\\b", "", ".hidden", "x" * 65])
def test_run_ids_cannot_leave_the_runs_folder(runs, bad):
    with pytest.raises(ra.RunNotFound, match="Invalid run id"):
        ra.load_run(bad, runs)


def test_unknown_run_id(runs):
    with pytest.raises(ra.RunNotFound, match="No run folder"):
        ra.load_run("20990101-000000-ffffff", runs)


# ------------------------------------------------------------------ insights


def test_fallback_insights_are_recognized_and_the_marker_is_removed(runs):
    text = f"{ra.FALLBACK_MARKER}\n> **Fallback insights.** Reason.\n\n# Insights\n"
    (runs / FAILED / "insights.md").write_text(text, encoding="utf-8")
    shown, fallback = ra.load_run(FAILED, runs).insights()
    assert fallback is True and ra.FALLBACK_MARKER not in shown
    assert shown.startswith("> **Fallback insights.**")


def test_agent_insights_are_shown_unchanged(runs):
    (runs / DONE / "insights.md").write_text("# Insights\n", encoding="utf-8")
    assert ra.load_run(DONE, runs).insights() == ("# Insights\n", False)
    (runs / DONE / "insights.md").unlink()
    assert ra.load_run(DONE, runs).insights() == (None, False)


# ------------------------------------------------- agreement with the runner


def test_names_match_the_crew1_runner():
    from src.crews import data_analyst_crew as c1

    assert set(ra.CREW1_FILES) == set(c1.REQUIRED_OUTPUTS)
    assert ra.REPORT_FILE == c1.REPORT_FILE
    assert ra.FALLBACK_MARKER == c1.FALLBACK_MARKER
