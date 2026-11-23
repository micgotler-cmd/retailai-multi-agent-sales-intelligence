"""Crew 1 with a scripted fake LLM: real agents, real tools, synthetic data, no network."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src.agents.data_analyst_agents import ANALYST_MAX_ITER, MAX_ITER
from src.crews import data_analyst_crew as c1
from src.tools import data_tools as dt
from tests.conftest import ITEMS, write_scope_file
from tests.fake_llm import action, fake_llm, final

RUN_ID = "test-run"
CAPS = {"max_calls": 100, "max_tokens": 1_000_000}  # generous: not the subject here


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any connection to a non-local address fails the test (no LLM API, no telemetry).

    Loopback is allowed: on Windows, asyncio (used by CrewAI) connects a socket pair
    to 127.0.0.1 for internal signalling; that never leaves the machine.
    """
    import socket

    real_connect = socket.socket.connect

    def guarded(sock, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"Network access attempted in a test: {address}")
        return real_connect(sock, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture
def setup(m5_raw_dir: Path, tmp_path: Path):
    scope = write_scope_file(tmp_path / "scope.json", ITEMS)
    runs = tmp_path / "runs"
    return m5_raw_dir, scope, runs, runs / RUN_ID


def template_insights(run_dir: Path):
    """Agent 3's answer: the Python template insights from this run (passes the check)."""
    return lambda _messages: action(
        "save_insights", markdown=(run_dir / dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    )


def happy_script(run_dir: Path) -> list:
    return [
        action("validate_raw_data"),
        final("Validation passed with no blocking failures."),
        action("build_clean_data"),
        final("Cleaning finished."),
        action("run_eda"),
        action("write_dataset_contract"),
        template_insights(run_dir),
        final("Insights saved."),
    ]


def run(setup, script) -> c1.Crew1Result:
    raw, scope, runs, _ = setup
    return c1.run_data_analyst_crew(fake_llm(script), raw, scope, runs, RUN_ID, **CAPS)


# ---------------------------------------------------------------- definitions


def test_crew_has_three_agents_and_ordered_tasks(setup):
    raw, scope, _runs, run_dir = setup
    crew = c1.build_crew(fake_llm([]), dt.RunPaths(raw, scope, run_dir))
    assert [a.role for a in crew.agents] == ["Data Validator", "Data Cleaner", "Business Analyst"]
    assert [t.agent.role for t in crew.tasks] == [a.role for a in crew.agents]
    tools = [[t.name for t in a.tools] for a in crew.agents]
    assert tools == [
        ["validate_raw_data"],
        ["build_clean_data"],
        ["run_eda", "write_dataset_contract", "save_insights"],
    ]
    assert [a.max_iter for a in crew.agents] == [MAX_ITER, MAX_ITER, ANALYST_MAX_ITER]
    assert not any(a.allow_delegation for a in crew.agents)
    assert crew.tasks[2].context == crew.tasks[:2]


def test_telemetry_is_disabled(setup):
    run(setup, happy_script(setup[3]))
    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true"
    assert os.environ["OTEL_SDK_DISABLED"] == "true"
    assert os.environ["CREWAI_TRACING_ENABLED"] == "false"


# ------------------------------------------------------------------- happy path


def test_full_run_writes_all_crew1_artifacts(setup):
    run_dir = setup[3]
    result = run(setup, happy_script(run_dir))
    assert result.status == "completed", result.problems
    assert result.insights_source == "agent" and result.problems == []
    assert all(result.artifacts.values())
    for name in ("clean_data.csv", "eda_report.html", "insights.md", "dataset_contract.json"):
        assert (run_dir / name).is_file()  # the four M-02 artifacts
    report = json.loads((run_dir / c1.REPORT_FILE).read_text(encoding="utf-8"))
    assert report["run_id"] == RUN_ID and report["status"] == "completed"
    assert len(report["agent_summaries"]) == 3
    assert "token_usage" not in report  # CrewAI's crew-level count overcounts a shared LLM


def test_each_agent_used_its_tools_once(setup):
    run_dir = setup[3]
    script = happy_script(run_dir)
    llm = fake_llm(script)
    raw, scope, runs, _ = setup
    c1.run_data_analyst_crew(llm, raw, scope, runs, RUN_ID, **CAPS)
    assert len(llm.calls) == 8 and llm.responses == []  # exactly the scripted steps


# --------------------------------------------------------------------- failures


def test_invented_numbers_fall_back_to_template(setup):
    run_dir = setup[3]
    bad = "# Insights\n\nSales will grow 15% next year, not causal."
    script = happy_script(run_dir)
    script[6:8] = [
        action("save_insights", markdown=bad),
        action("save_insights", markdown=bad),
        final("I could not save the insights."),
    ]
    result = run(setup, script)
    assert result.status == "completed"
    assert result.insights_source == "template"
    assert any("template insights were used" in p for p in result.problems)
    saved = (run_dir / "insights.md").read_text(encoding="utf-8")
    assert saved == (run_dir / dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    assert "15%" not in saved


def test_validation_failure_stops_the_pipeline(setup):
    raw, _, _, run_dir = setup
    cal = pd.read_csv(raw / "calendar.csv")
    cal.drop(index=[30]).to_csv(raw / "calendar.csv", index=False)
    script = [
        action("validate_raw_data"),
        final("Validation failed: calendar dates are missing."),
        final("Cleaning skipped because validation failed."),
        final("Analysis skipped: no clean data."),
    ]
    result = run(setup, script)
    assert result.status == "failed"
    assert not (run_dir / "clean_data.csv").exists()
    assert "quality_report.json status is not pass" in result.problems


def test_agent_cannot_clean_after_failed_validation(setup):
    """Even if the agent ignores the failure and calls the tool, the tool refuses."""
    raw, _, _, run_dir = setup
    cal = pd.read_csv(raw / "calendar.csv")
    cal.drop(index=[30]).to_csv(raw / "calendar.csv", index=False)
    script = [
        action("validate_raw_data"),
        final("Validation failed."),
        action("build_clean_data"),
        final("The cleaning tool refused."),
        final("Analysis skipped."),
    ]
    result = run(setup, script)
    assert result.status == "failed"
    assert not (run_dir / "clean_data.csv").exists()


def test_llm_error_fails_cleanly(setup):
    run_dir = setup[3]
    result = run(setup, [])  # the fake LLM raises on its first call
    assert result.status == "failed"
    assert any(p.startswith("Crew error") for p in result.problems)
    assert (run_dir / c1.REPORT_FILE).is_file()


def test_run_folder_is_never_reused(setup):
    run(setup, happy_script(setup[3]))
    with pytest.raises(FileExistsError):
        run(setup, happy_script(setup[3]))


def test_network_guard_blocks_outside_addresses():
    import socket

    with socket.socket() as sock, pytest.raises(AssertionError, match="Network access"):
        sock.connect(("8.8.8.8", 53))  # blocked before any packet is sent


def test_new_run_ids_are_unique():
    assert c1.new_run_id() != c1.new_run_id()


def test_cli_without_llm_settings_fails(tmp_path: Path, monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    assert c1.main(["--runs-dir", str(tmp_path / "runs")]) == 1
    assert not (tmp_path / "runs").exists()  # nothing created, no API call


# ------------------------------------------------------------------ LLM budget


def run_capped(setup, script, tokens_per_call=0, **caps):
    raw, scope, runs, _ = setup
    llm = fake_llm(script, tokens_per_call=tokens_per_call)
    return llm, c1.run_data_analyst_crew(llm, raw, scope, runs, RUN_ID, **caps)


def test_call_cap_stops_the_run(setup):
    llm, result = run_capped(setup, happy_script(setup[3]), max_calls=3, max_tokens=1_000_000)
    assert len(llm.calls) == 3  # the 4th call never reached the model
    assert result.status == "failed"
    assert result.llm_budget["calls"] == 3
    assert "call cap reached" in result.llm_budget["stop_reason"]
    assert any("Stopped by the LLM budget" in p for p in result.problems)
    # Calls 1-3: validate, validator answer, clean. Call 4 (the cleaner's answer) is blocked,
    # so the analyst never runs.
    assert (setup[3] / "clean_data.csv").exists()
    assert not (setup[3] / "eda_summary.json").exists()


def test_token_cap_stops_the_run(setup):
    # 1,000 tokens per call; cap 2,500: calls 1-3 start below the cap, call 4 is blocked.
    llm, result = run_capped(
        setup, happy_script(setup[3]), tokens_per_call=1000, max_calls=100, max_tokens=2500
    )
    assert len(llm.calls) == 3
    assert result.status == "failed"
    assert result.llm_budget["tokens"] == 3000
    assert "token cap reached" in result.llm_budget["stop_reason"]


def test_budget_usage_is_reported(setup):
    _, result = run_capped(
        setup, happy_script(setup[3]), tokens_per_call=100, max_calls=8, max_tokens=800
    )
    assert result.status == "completed"  # exactly at the caps, nothing blocked
    assert result.llm_budget == {
        "calls": 8,
        "max_calls": 8,
        "tokens": 800,
        "max_tokens": 800,
        "stop_reason": None,
    }
    report = json.loads((setup[3] / c1.REPORT_FILE).read_text(encoding="utf-8"))
    assert report["llm_budget"]["calls"] == 8


def test_budget_hook_is_removed_after_the_run(setup):
    from crewai.hooks import get_before_llm_call_hooks

    before = len(get_before_llm_call_hooks())
    run_capped(setup, [], max_calls=5, max_tokens=1000)  # fails inside the crew
    assert len(get_before_llm_call_hooks()) == before


def test_caps_are_required(setup):
    raw, scope, runs, _ = setup
    with pytest.raises(TypeError):
        c1.run_data_analyst_crew(fake_llm([]), raw, scope, runs, RUN_ID)  # no caps given
