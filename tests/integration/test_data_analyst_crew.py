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


def bad(n: int) -> str:
    """Insights with an invented number. A new text per attempt: CrewAI refuses a tool call
    that exactly repeats the previous one, without running the tool."""
    return f"# Insights\n\nSales will grow 1{n}% next year, not causal."


def test_invented_numbers_fall_back_to_labeled_template(setup, caplog):
    run_dir = setup[3]
    script = happy_script(run_dir)
    script[6:8] = [
        action("save_insights", markdown=bad(1)),
        action("save_insights", markdown=bad(2)),
        final("I could not save the insights."),
    ]
    with caplog.at_level("INFO"):
        result = run(setup, script)
    assert result.status == "completed"
    assert result.insights_source == "template" and result.insights_attempts == 2
    assert result.fallback_reason == (
        "Agent 3 stopped after 2 rejected attempt(s) (2 problems in the last one)"
    )
    assert any("template insights were used" in p for p in result.problems)
    saved = (run_dir / "insights.md").read_text(encoding="utf-8")
    template = (run_dir / dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
    assert saved.startswith(c1.FALLBACK_MARKER) and "**Fallback insights.**" in saved
    assert result.fallback_reason in saved and saved.endswith(template)
    assert "11%" not in saved and "12%" not in saved
    report = json.loads((run_dir / c1.REPORT_FILE).read_text(encoding="utf-8"))
    assert report["insights_source"] == "template"
    assert report["fallback_reason"] == result.fallback_reason
    assert report["insights_attempts"] == 2
    log = caplog.text  # failures, retries, fallback reason and token usage are logged
    assert "Insights attempt 1 rejected with 2 problems" in log
    assert "Insights attempt 2 rejected" in log
    assert "Using template insights" in log and result.fallback_reason in log
    assert "LLM usage of run test-run: 9 calls, 0 tokens" in log


def test_retries_are_limited(setup):
    run_dir = setup[3]
    script = happy_script(run_dir)
    script[6:8] = [
        action("save_insights", markdown=bad(i)) for i in range(dt.MAX_SAVE_ATTEMPTS)
    ] + [
        template_insights(run_dir),  # a valid text after the limit is refused
        final("No attempts left."),
    ]
    result = run(setup, script)
    assert result.insights_source == "template"
    assert result.insights_attempts == dt.MAX_SAVE_ATTEMPTS
    assert result.fallback_reason.startswith(
        f"the citation check rejected all {dt.MAX_SAVE_ATTEMPTS} attempts"
    )


def test_agent_insights_after_one_correction(setup):
    run_dir = setup[3]
    script = happy_script(run_dir)
    script[6:6] = [action("save_insights", markdown=bad(0))]
    result = run(setup, script)
    assert result.insights_source == "agent" and result.insights_attempts == 2
    assert result.fallback_reason is None and result.problems == []
    saved = (run_dir / "insights.md").read_text(encoding="utf-8")
    assert not saved.startswith(c1.FALLBACK_MARKER)


def test_budget_stop_is_the_fallback_reason(setup):
    _, result = run_capped(setup, happy_script(setup[3]), max_calls=6, max_tokens=1_000_000)
    assert result.insights_source == "template"
    assert result.fallback_reason.startswith("the run was stopped by the LLM budget")


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


def test_report_is_redacted(setup):
    """Phase gate: an error message that echoes a key must not reach crew1_report.json."""
    raw, scope, runs, run_dir = setup

    def leaky(_messages):
        raise RuntimeError("auth failed for sk-test1234567890abcdef and local-secret-42")

    result = c1.run_data_analyst_crew(
        fake_llm([leaky] * 10), raw, scope, runs, RUN_ID, **CAPS, secrets=["local-secret-42"]
    )
    report = (run_dir / c1.REPORT_FILE).read_text(encoding="utf-8")
    assert result.status == "failed" and "***REDACTED***" in report
    assert "sk-test1234567890abcdef" not in report and "local-secret-42" not in report


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
