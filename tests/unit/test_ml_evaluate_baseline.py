"""Tests for the baseline evaluation command: outputs, isolation of the test window, failures."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ml import evaluate_baseline as ev
from tests.conftest import ITEMS, N_DAYS, make_scope, write_scope_file
from tests.ml_data import day_date, make_clean


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    scope_path = write_scope_file(tmp_path / "scope.json")
    clean_path = tmp_path / "clean" / "clean_data.csv"
    clean_path.parent.mkdir()
    make_clean().to_csv(clean_path, index=False)
    return {"scope": scope_path, "clean": clean_path, "out": tmp_path / "out"}


def run(paths: dict[str, Path], *extra: str) -> int:
    return ev.main(
        [
            "--clean-data",
            str(paths["clean"]),
            "--scope",
            str(paths["scope"]),
            "--out-dir",
            str(paths["out"]),
            *extra,
        ]
    )


def test_run_writes_metrics_and_test_forecast(paths):
    assert run(paths, "--run-id", "r1") == 0
    metrics = json.loads((paths["out"] / ev.METRICS_FILE).read_text())
    assert metrics["model"] == "seasonal_naive"
    assert metrics["run_id"] == "r1"
    assert [w["window"] for w in metrics["backtest"]["windows"]] == [
        "backtest_1",
        "backtest_2",
        "backtest_3",
    ]
    assert set(metrics["test"]["per_item"]) == set(ITEMS)
    assert set(metrics["test"]["per_demand_group"]) == {"high"}
    assert metrics["test"]["window"] == "test"
    assert metrics["backtest"]["mean_overall"]["mae"] > 0
    forecast = pd.read_csv(paths["out"] / ev.TEST_FORECAST_FILE)
    assert list(forecast.columns) == [
        "run_id",
        "store_id",
        "item_id",
        "forecast_date",
        "model",
        "predicted_units",
    ]
    assert len(forecast) == 28 * len(ITEMS)
    assert forecast["forecast_date"].min() == str(day_date(N_DAYS - 27).date())
    assert forecast["forecast_date"].max() == str(day_date(N_DAYS).date())


def test_outputs_hold_no_actual_sales_columns(paths):
    run(paths)
    forecast = pd.read_csv(paths["out"] / ev.TEST_FORECAST_FILE)
    assert "units_sold" not in forecast.columns and "actual_units" not in forecast.columns
    assert "units_sold" not in (paths["out"] / ev.METRICS_FILE).read_text()


def test_test_score_matches_an_independent_computation(paths):
    run(paths)
    clean = pd.read_csv(paths["clean"], parse_dates=["date"])
    scope = make_scope()
    origin_day = scope.split["test"].first_day - 1
    errors = []
    for item in ITEMS:
        rows = clean[clean["item_id"] == item].set_index("date")["units_sold"]
        last_week = [rows[day_date(d)] for d in range(origin_day - 6, origin_day + 1)]
        for step in range(28):
            errors.append(rows[day_date(origin_day + 1 + step)] - last_week[step % 7])
    errors = np.array(errors, dtype=float)
    metrics = json.loads((paths["out"] / ev.METRICS_FILE).read_text())
    assert metrics["test"]["overall"]["mae"] == pytest.approx(np.abs(errors).mean(), abs=1e-6)
    assert metrics["test"]["overall"]["rmse"] == pytest.approx(
        np.sqrt((errors**2).mean()), abs=1e-6
    )


def test_changing_test_window_actuals_changes_neither_forecast_nor_backtest(paths, tmp_path):
    run(paths)
    first_metrics = json.loads((paths["out"] / ev.METRICS_FILE).read_text())
    first_forecast = (paths["out"] / ev.TEST_FORECAST_FILE).read_text()
    clean = pd.read_csv(paths["clean"], parse_dates=["date"])
    clean.loc[clean["date"] >= day_date(N_DAYS - 27), "units_sold"] = 5000
    changed = {**paths, "clean": tmp_path / "changed.csv", "out": tmp_path / "out2"}
    clean.to_csv(changed["clean"], index=False)
    assert run(changed) == 0
    second_metrics = json.loads((changed["out"] / ev.METRICS_FILE).read_text())
    assert (changed["out"] / ev.TEST_FORECAST_FILE).read_text() == first_forecast
    assert second_metrics["backtest"] == first_metrics["backtest"]
    assert second_metrics["test"]["overall"]["mae"] > first_metrics["test"]["overall"]["mae"]


def test_two_runs_give_identical_files(paths, tmp_path):
    run(paths)
    other = {**paths, "out": tmp_path / "out_again"}
    run(other)
    for name in (ev.METRICS_FILE, ev.TEST_FORECAST_FILE):
        assert (paths["out"] / name).read_bytes() == (other["out"] / name).read_bytes()


def test_output_folder_is_configurable_and_default_is_artifacts_ml(paths):
    assert ev.DEFAULT_OUT_DIR == Path("artifacts/ml")
    nested = {**paths, "out": paths["out"] / "runs" / "abc"}
    assert run(nested) == 0
    assert (nested["out"] / ev.METRICS_FILE).exists()


def test_default_output_folder_is_ignored_by_git():
    if shutil.which("git") is None:
        pytest.skip("git not available")
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        ["git", "check-ignore", "-q", str(ev.DEFAULT_OUT_DIR / ev.METRICS_FILE)],
        cwd=root,
        check=False,
    )
    if probe.returncode == 128:
        pytest.skip("not a git repository")
    assert probe.returncode == 0


def seed_stale(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in (ev.METRICS_FILE, ev.TEST_FORECAST_FILE):
        (out / name).write_text("STALE")
        (out / f"{name}.tmp").write_text("STALE")


def assert_no_outputs(out: Path) -> None:
    assert not any((out / n).exists() for n in (ev.METRICS_FILE, ev.TEST_FORECAST_FILE))
    assert not list(out.glob("*.tmp"))


def test_insufficient_history_fails_and_leaves_no_stale_outputs(paths):
    clean = pd.read_csv(paths["clean"], parse_dates=["date"])
    # FOODS_1_001 starts only 3 days before the first backtest origin (day 88)
    drop = (clean["item_id"] == ITEMS[0]) & (clean["date"] < day_date(86))
    clean[~drop].to_csv(paths["clean"], index=False)
    seed_stale(paths["out"])
    assert run(paths) == 1
    assert_no_outputs(paths["out"])


def test_missing_clean_data_fails_and_leaves_no_stale_outputs(paths):
    paths["clean"].unlink()
    seed_stale(paths["out"])
    assert run(paths) == 1
    assert_no_outputs(paths["out"])


def test_items_that_disagree_with_the_scope_fail(paths):
    clean = pd.read_csv(paths["clean"], parse_dates=["date"])
    clean[clean["item_id"] != ITEMS[0]].to_csv(paths["clean"], index=False)
    seed_stale(paths["out"])
    assert run(paths) == 1
    assert_no_outputs(paths["out"])


def test_missing_columns_in_clean_data_fail(paths):
    pd.read_csv(paths["clean"]).drop(columns="units_sold").to_csv(paths["clean"], index=False)
    assert run(paths) == 1
    assert_no_outputs(paths["out"])


def test_a_hole_before_an_origin_fails(paths):
    clean = pd.read_csv(paths["clean"], parse_dates=["date"])
    hole = (clean["item_id"] == ITEMS[1]) & (clean["date"] == day_date(N_DAYS - 29))  # day 171
    clean[~hole].to_csv(paths["clean"], index=False)
    assert run(paths) == 1  # the test origin's last week now has a missing day
    assert_no_outputs(paths["out"])
