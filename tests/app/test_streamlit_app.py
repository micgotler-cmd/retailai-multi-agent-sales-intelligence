"""Smoke tests of the Streamlit app with fixture run folders (P-13, testing-strategy.md).

Each page must load without an exception, with runs and without any run.
AppTest runs the scripts in this process: no browser, no network, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import common
from src.repositories import run_artifacts as ra

APP = str(Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py")
PAGES = ["pages/home.py", "pages/data_quality.py", "pages/eda.py", "pages/insights.py"]
DONE = "20261124-164623-7d1d1d"
OLDER = "20261123-182519-44fd68"
FAILED = "20261125-080000-bbbbbb"


def write_run(runs: Path, run_id: str, report: dict | None, files=ra.CREW1_FILES) -> None:
    path = runs / run_id
    path.mkdir(parents=True)
    for name in files:
        (path / name).write_text("{}" if name.endswith(".json") else "x", encoding="utf-8")
    if report is not None:
        (path / ra.REPORT_FILE).write_text(json.dumps(report), encoding="utf-8")


def report(status="completed", source="agent", problems=(), reason=None) -> dict:
    return {
        "run_id": "x",
        "status": status,
        "insights_source": source,
        "fallback_reason": reason,
        "problems": list(problems),
        "llm_budget": {"calls": 10, "max_calls": 100, "tokens": 44069, "max_tokens": 200000},
    }


@pytest.fixture
def runs(tmp_path: Path, monkeypatch) -> Path:
    runs = tmp_path / "runs"
    write_run(runs, DONE, report())
    write_run(runs, OLDER, report(source="template", reason="Agent 3 did not call save_insights"))
    write_run(
        runs, FAILED, report("failed", "none", ["Crew error: boom"]), files=ra.CREW1_FILES[:1]
    )
    monkeypatch.setenv(common.RUNS_DIR_ENV, str(runs))
    return runs


def start(page: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    if page:
        at.switch_page(page)
        at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [e.value for e in at.info] + [e.body for e in at.error]
    parts += (
        [e.value for e in at.success] + [e.value for e in at.warning] + [c.value for c in at.code]
    )
    parts += [str(m.value) for m in at.metric] + [m.label for m in at.metric]
    return "\n".join(str(p) for p in parts)


# ----------------------------------------------------------- with fixture runs


@pytest.mark.parametrize("page", PAGES)
def test_every_page_loads(runs, page):
    start(page)


def test_run_picker_defaults_to_the_newest_completed_run(runs):
    at = start()
    picker = at.sidebar.selectbox[0]
    assert picker.value == DONE  # the newer FAILED run is listed but not the default
    assert picker.options[0].startswith("2026-11-25 08:00 UTC · failed")
    assert len(picker.options) == 3


def test_home_shows_status_usage_and_outputs(runs):
    at = start()
    shown = text(at)
    assert "Crew 1 status: **completed**" in shown
    assert "Business Analyst agent" in shown
    assert "10 / 100" in shown and "44,069 / 200,000" in shown
    assert "CA_1" in shown and "28 days" in shown
    files = at.dataframe[0].value
    assert list(files["File"]) == list(ra.CREW1_FILES) and files["Present"].all()


def test_home_shows_fallback_and_problems_of_another_run(runs):
    at = start()
    at.sidebar.selectbox[0].set_value(OLDER).run()
    assert not at.exception
    shown = text(at)
    assert "Template (fallback)" in shown
    assert "Fallback reason: Agent 3 did not call save_insights" in shown


def test_home_marks_a_failed_run_and_missing_files(runs):
    at = start()
    at.sidebar.selectbox[0].set_value(FAILED).run()
    assert not at.exception
    assert any("failed" in e.body for e in at.error)
    assert at.expander[0].label == "Problems recorded (1)"
    files = at.dataframe[0].value
    assert files["Present"].sum() == 1


def test_run_without_report_shows_a_message(runs):
    write_run(runs, "20261126-000000-cccccc", None, files=())
    at = start()
    at.sidebar.selectbox[0].set_value("20261126-000000-cccccc").run()
    assert not at.exception
    assert any("no crew1_report.json" in w.value for w in at.warning)


# ------------------------------------------------------------------- no runs


@pytest.mark.parametrize("page", PAGES)
def test_pages_without_any_run_show_the_run_command(tmp_path, monkeypatch, page):
    monkeypatch.setenv(common.RUNS_DIR_ENV, str(tmp_path / "no-runs-yet"))
    at = start(page)
    assert any("No pipeline run found yet" in i.value for i in at.info)
    assert any(common.RUN_COMMAND in c.value for c in at.code)


# --------------------------------------------------------------- app settings


def test_streamlit_usage_statistics_are_off():
    import tomllib

    config = tomllib.loads(Path(".streamlit/config.toml").read_text(encoding="utf-8"))
    assert config["browser"]["gatherUsageStats"] is False
    assert config["server"]["address"] == "localhost"


def test_chosen_run_is_kept_when_changing_page(runs):
    """AppTest drops sidebar widgets from its element tree after a rerun under
    st.navigation (the app itself keeps them), so the page content is checked."""
    at = start()
    at.sidebar.selectbox[0].set_value(OLDER).run()
    at.switch_page("pages/eda.py")
    at.run()
    assert not at.exception
    assert any(OLDER in i.value for i in at.info)
