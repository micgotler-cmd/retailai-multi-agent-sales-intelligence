"""End-to-end test of Crew 1 (phase gate after P-04): the full crew through its runner.

Real agents, real tools and the real runner, with a scripted fake LLM (no API
call, no cost, no network). Checks what the next phase (the Flow, Gate 1 and
Crew 2) relies on: the eight Crew 1 files exist, the clean data passes its
contract, the data is identical to the deterministic data pipeline's, and no
data rows are ever sent to the LLM (T-04 condition 6). The real-data test runs
only when the M5 files are in data/raw/ (never in the repository).
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from src.crews import data_analyst_crew as c1
from src.data import cleaning
from src.tools import data_tools as dt
from tests.conftest import ITEMS, write_scope_file
from tests.fake_llm import action, fake_llm, final

REAL_RAW = Path("data/raw")
REAL_FILES = ["calendar.csv", "sales_train_evaluation.csv", "sell_prices.csv"]
CAPS = {"max_calls": 100, "max_tokens": 1_000_000}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any connection to a non-local address fails the test (loopback: asyncio on Windows)."""
    real_connect = socket.socket.connect

    def guarded(sock, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"Network access attempted in a test: {address}")
        return real_connect(sock, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded)


def script(run_dir: Path) -> list:
    """The approved order: validate, clean, EDA, contract, insights (the template text)."""
    return [
        action("validate_raw_data"),
        final("Validation passed."),
        action("build_clean_data"),
        final("Cleaning finished."),
        action("run_eda"),
        action("write_dataset_contract"),
        lambda _m: action(
            "save_insights", markdown=(run_dir / dt.INSIGHTS_TEMPLATE).read_text(encoding="utf-8")
        ),
        final("Insights saved."),
    ]


def run_crew1(raw: Path, scope: Path, runs: Path):
    run_dir = runs / "e2e"
    llm = fake_llm(script(run_dir))
    result = c1.run_data_analyst_crew(llm, raw, scope, runs, "e2e", **CAPS)
    return result, run_dir, llm


def check_run(result, run_dir: Path, llm, raw: Path, scope: Path, tmp_path: Path) -> None:
    assert result.status == "completed", result.problems
    assert result.problems == [] and result.insights_source == "agent"
    assert all(result.artifacts.values()) and set(result.artifacts) == set(c1.REQUIRED_OUTPUTS)
    for name in (dt.QUALITY_REPORT, dt.CONTRACT_CHECK):
        assert json.loads((run_dir / name).read_text(encoding="utf-8"))["status"] == "pass"

    # The crew's clean data is byte-identical to the deterministic pipeline's.
    out = tmp_path / "pipeline"
    assert cleaning.main(["--raw-dir", str(raw), "--scope", str(scope), "--out-dir", str(out)]) == 0
    assert (run_dir / dt.CLEAN_DATA).read_bytes() == (out / dt.CLEAN_DATA).read_bytes()

    # No data rows reach the LLM: no line of clean_data.csv appears in any prompt.
    prompts = json.dumps(llm.calls, default=str)
    lines = (run_dir / dt.CLEAN_DATA).read_text(encoding="utf-8").splitlines()
    assert not any(line in prompts for line in lines[:200])

    report = json.loads((run_dir / c1.REPORT_FILE).read_text(encoding="utf-8"))
    assert report["llm_budget"]["calls"] == 8 and report["fallback_reason"] is None


def test_crew1_end_to_end_on_synthetic_data(m5_raw_dir: Path, tmp_path: Path):
    scope = write_scope_file(tmp_path / "scope.json", ITEMS + ["HOBBIES_1_003"])
    result, run_dir, llm = run_crew1(m5_raw_dir, scope, tmp_path / "runs")
    check_run(result, run_dir, llm, m5_raw_dir, scope, tmp_path)


@pytest.mark.skipif(
    not all((REAL_RAW / f).is_file() for f in REAL_FILES),
    reason="M5 files not in data/raw/ (download them from Kaggle, see README)",
)
def test_crew1_end_to_end_on_real_data(tmp_path: Path):
    scope = Path("config/data_scope.json")
    result, run_dir, llm = run_crew1(REAL_RAW, scope, tmp_path / "runs")
    check_run(result, run_dir, llm, REAL_RAW, scope, tmp_path)
    log = json.loads((run_dir / dt.CLEANING_LOG).read_text(encoding="utf-8"))
    assert (log["rows_in"], log["rows_out"]) == (38_820, 31_278)
