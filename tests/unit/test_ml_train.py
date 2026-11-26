"""Tests for the models and the training pipeline: grids, isolation of the test window,
leakage, clipping, reproducibility, outputs and failure handling."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from src.ml import feature_spec as spec
from src.ml import features as ft
from src.ml import models, train
from src.ml.metrics import score_forecast
from src.ml.models import Candidate, ModelError
from src.ml.windows import final_test_window, future_window
from tests.conftest import N_DAYS, make_scope, write_scope_file
from tests.ml_data import day_date, make_calendar, make_clean, with_ids

TEST_FIRST = N_DAYS - 27  # 173
TRAIN_LAST_FOR_TEST = TEST_FIRST - 1  # 172


@pytest.fixture(autouse=True)
def small_grids(monkeypatch):
    """Keep the pipeline tests fast; the real grids are checked in their own test."""
    monkeypatch.setattr(
        models,
        "GRIDS",
        {
            models.RIDGE: {"alpha": [1.0, 100.0]},
            models.RANDOM_FOREST: {
                "n_estimators": [10],
                "max_depth": [3, 6],
                "min_samples_leaf": [5],
            },
        },
    )


@pytest.fixture
def scope():
    return make_scope()


@pytest.fixture
def clean():
    return with_ids(make_clean())


def build(clean, scope):
    return ft.build_features(clean, make_calendar(), scope)


@pytest.fixture
def features(clean, scope):
    return build(clean, scope)


@pytest.fixture
def result(features, clean, scope):
    return train.run(features, clean, scope, "run-1")


def perturb_days(clean: pd.DataFrame, first_day: int, amount: float = 500.0) -> pd.DataFrame:
    changed = clean.copy()
    changed.loc[changed["date"] >= day_date(first_day), "units_sold"] += amount
    return changed


# --- models -------------------------------------------------------------------------------


def test_approved_grids(monkeypatch):
    monkeypatch.undo()  # the real grids
    assert models.RIDGE_GRID == {"alpha": [0.1, 1.0, 10.0, 100.0]}
    assert models.RANDOM_FOREST_GRID == {
        "n_estimators": [100, 300],
        "max_depth": [8, 16],
        "min_samples_leaf": [5, 20],
    }
    found = models.candidates()
    assert sum(c.variant == models.RIDGE for c in found) == 4
    assert sum(c.variant == models.RANDOM_FOREST for c in found) == 8
    assert len({(c.variant, tuple(c.params.items())) for c in found}) == 12


def test_predictions_are_never_negative(features, scope):
    rows = ft.training_rows(features, scope.split["train"].last_day)
    pipeline = models.fit(Candidate(models.RIDGE, {"alpha": 1.0}), rows)
    for size in (-5000.0, 5000.0):  # one of the two directions drives Ridge below zero
        extreme = rows.head(20).assign(lag_28=size, lag_35=size, roll_mean_28=size)
        assert (models.predict_units(pipeline, extreme) >= 0).all()
    raw = [
        pipeline.predict(
            rows.head(20).assign(lag_28=size, lag_35=size, roll_mean_28=size)[spec.FEATURE_COLUMNS]
        )
        for size in (-5000.0, 5000.0)
    ]
    assert min(r.min() for r in raw) < 0  # the clipping is doing real work


def test_model_errors(features):
    with pytest.raises(ModelError, match="Unknown"):
        models.make_pipeline(Candidate("gradient_boosting"))
    with pytest.raises(ModelError, match="No training rows"):
        models.fit(Candidate(models.RIDGE, {"alpha": 1.0}), features.iloc[0:0])
    incomplete = features.head(50).copy()  # early rows have no lags
    with pytest.raises(ModelError, match="complete"):
        models.fit(Candidate(models.RIDGE, {"alpha": 1.0}), incomplete)
    rows = ft.training_rows(features, 120)
    pipeline = models.fit(Candidate(models.RIDGE, {"alpha": 1.0}), rows)
    with pytest.raises(ModelError, match="missing"):
        models.predict_units(pipeline, features.head(5))


def test_unseen_category_is_ignored_not_fatal(features):
    rows = ft.training_rows(features, 120)
    pipeline = models.fit(Candidate(models.RANDOM_FOREST, {"n_estimators": 5}), rows)
    unseen = rows.head(3).assign(event_type_1="Brand new event")
    assert np.isfinite(models.predict_units(pipeline, unseen)).all()


# --- pipeline results ---------------------------------------------------------------------


def test_selection_uses_the_backtest_metric_only(result):
    metrics = result[0]
    selection = metrics["selection"]
    assert selection["metric"].startswith("mean overall MAE")
    scores = {}
    for entry in metrics["backtest_candidates"]:
        scores.setdefault(entry["model"], []).append(entry["mean_overall"]["mae"])
    best = {variant: min(values) for variant, values in scores.items()}
    assert metrics["selected_model"] == min(models.VARIANTS, key=lambda v: best[v])
    assert selection["selected_mean_backtest_mae"] == best[metrics["selected_model"]]
    assert (
        metrics["models"][metrics["selected_model"]]["backtest"]["mean_overall"]["mae"]
        == (best[metrics["selected_model"]])
    )
    assert len(metrics["backtest_candidates"]) == 4  # 2 ridge + 2 forest in the test grids
    assert [w["window"] for w in metrics["models"]["ridge"]["backtest"]["windows"]] == [
        "backtest_1",
        "backtest_2",
        "backtest_3",
    ]


def test_test_metrics_come_from_a_model_fitted_before_the_test_window(result, clean, scope):
    metrics, test_forecast, _, _ = result
    test = metrics["test"]
    assert test["fitted_through_day"] == TRAIN_LAST_FOR_TEST
    assert metrics["refit"]["fitted_through_day"] == scope.last_day
    actual = clean[clean["date"] >= day_date(TEST_FIRST)]
    again = score_forecast(test_forecast, actual, scope.items)
    assert again["overall"] == test["overall"]
    assert test["seasonal_naive"]["overall"]["mae"] > 0
    assert test["improvement_over_baseline_mae"] == pytest.approx(
        test["seasonal_naive"]["overall"]["mae"] - test["overall"]["mae"], abs=1e-6
    )


def test_model_version_identifies_the_refitted_model(result, scope):
    metrics, test_forecast, forecast, bundle = result
    expected = f"{metrics['selected_model']}-d{scope.last_day}-run-1"
    assert (forecast["model_version"] == expected).all()
    assert metrics["refit"]["model_version"] == bundle["model_version"] == expected
    assert train.model_version("ridge", 1941, "r1") == "ridge-d1941-r1"
    assert "model_version" not in test_forecast.columns  # the test forecast is not a future one
    assert (forecast["model"] == metrics["selected_model"]).all()


def test_only_the_selected_model_and_baseline_are_scored_on_the_test_window(result):
    metrics = result[0]
    unselected = [v for v in models.VARIANTS if v != metrics["selected_model"]]
    for variant in unselected:
        assert "test" not in metrics["models"][variant]
    assert metrics["models"]["seasonal_naive"].keys() == {"backtest"}


def test_forecast_tables_cover_the_right_days_and_hold_no_actuals(result, scope):
    _, test_forecast, forecast, _ = result
    test_window, future = final_test_window(scope), future_window(scope)
    for table, window, columns in (
        (test_forecast, test_window, train.TEST_FORECAST_COLUMNS),
        (forecast, future, train.FORECAST_COLUMNS),
    ):
        assert list(table.columns) == columns
        assert len(table) == window.n_days * len(scope.item_ids)
        assert table["forecast_date"].min() == day_date(window.first_day)
        assert table["forecast_date"].max() == day_date(window.last_day)
        assert (table["predicted_units"] >= 0).all()
        assert np.isfinite(table["predicted_units"]).all()
        assert "units_sold" not in table.columns and "actual_units" not in table.columns


def test_changing_test_window_sales_never_changes_selection_or_the_test_forecast(
    result, features, clean, scope
):
    """The test window is isolated: only the test score (against actuals) may move."""
    changed_clean = perturb_days(clean, TEST_FIRST)
    changed = train.run(build(changed_clean, scope), changed_clean, scope, "run-1")
    base, other = result[0], changed[0]
    assert other["selected_model"] == base["selected_model"]
    assert other["selection"] == base["selection"]
    assert other["backtest_candidates"] == base["backtest_candidates"]
    assert other["models"] == base["models"]
    pd.testing.assert_frame_equal(result[1], changed[1])  # same test predictions
    assert other["test"]["overall"] != base["test"]["overall"]  # the score does react


def test_refit_uses_all_history_but_test_forecast_does_not(result, clean, scope):
    """Sales on the last observed day reach the future forecast, not the test forecast."""
    last = clean.copy()
    last.loc[last["date"] == day_date(scope.last_day), "units_sold"] += 500
    other = train.run(build(last, scope), last, scope, "run-1")
    pd.testing.assert_frame_equal(result[1], other[1])
    assert not result[2].equals(other[2])


def test_backtest_scores_ignore_sales_after_each_window(result, clean, scope):
    """Changing sales after validation ends leaves every backtest score unchanged."""
    changed = perturb_days(clean, scope.split["validation"].last_day + 1)
    other = train.run(build(changed, scope), changed, scope, "run-1")
    assert other[0]["backtest_candidates"] == result[0]["backtest_candidates"]
    assert other[0]["models"]["ridge"] == result[0]["models"]["ridge"]


def test_results_are_reproducible(features, clean, scope, result):
    again = train.run(features, clean, scope, "run-1")
    assert again[0] == result[0]
    pd.testing.assert_frame_equal(again[1], result[1])
    pd.testing.assert_frame_equal(again[2], result[2])


def test_a_model_that_loses_to_the_baseline_is_reported_as_such(
    monkeypatch, features, clean, scope
):
    real = train.baseline_eval.evaluate

    def perfect_baseline(*args):
        metrics, forecast = real(*args)
        metrics["backtest"]["mean_overall"] = {"mae": 0.0, "rmse": 0.0}
        return metrics, forecast

    monkeypatch.setattr(train.baseline_eval, "evaluate", perfect_baseline)
    metrics = train.run(features, clean, scope, "run-1")[0]
    assert metrics["selection"]["beats_baseline_on_backtest"] is False
    assert metrics["selected_model"] in models.VARIANTS  # still one of the two ML variants


def test_all_zero_sales_give_zero_forecasts(scope):
    zero = with_ids(make_clean())
    zero["units_sold"] = 0
    metrics, test_forecast, forecast, _ = train.run(build(zero, scope), zero, scope, "run-1")
    assert (test_forecast["predicted_units"] >= 0).all() and (
        forecast["predicted_units"] >= 0
    ).all()
    assert metrics["test"]["overall"]["mae"] == pytest.approx(0.0, abs=1e-6)


def test_bundle_holds_both_variants_with_fitted_preprocessing(result, features, scope):
    metrics, _, forecast, bundle = result
    assert set(bundle["variants"]) == set(models.VARIANTS)
    assert bundle["selected_model"] == metrics["selected_model"]
    assert bundle["fitted_through_day"] == scope.last_day
    assert bundle["feature_columns"] == spec.FEATURE_COLUMNS
    for info in bundle["variants"].values():
        assert hasattr(info["pipeline"].named_steps["prep"], "transformers_")  # fitted
    rows = ft.forecast_rows(features, future_window(scope))
    chosen = bundle["variants"][bundle["selected_model"]]["pipeline"]
    expected = forecast.sort_values(["item_id", "forecast_date"])["predicted_units"].to_numpy()
    got = pd.Series(models.predict_units(chosen, rows), index=rows.index)
    got = got.groupby([rows["item_id"], rows["date"]]).first().to_numpy()
    assert np.allclose(got, expected)


def test_invalid_features_stop_the_run(features, clean, scope):
    broken = features.copy()
    broken.loc[broken["day"] == N_DAYS + 3, "lag_28"] = np.nan
    with pytest.raises(spec.FeatureError):
        train.run(broken, clean, scope, "run-1")


# --- the command ----------------------------------------------------------------------------


@pytest.fixture
def cli(tmp_path, clean, scope):
    clean_path = tmp_path / "clean.csv"
    clean.assign(store_closed=0).to_csv(clean_path, index=False)
    features_path = tmp_path / "features.csv"
    build(clean, scope).to_csv(features_path, index=False, date_format="%Y-%m-%d")
    scope_path = write_scope_file(tmp_path / "scope.json")
    return {
        "clean": clean_path,
        "features": features_path,
        "scope": scope_path,
        "out": tmp_path / "out",
    }


def run_cli(cli) -> int:
    return train.main(
        [
            "--features",
            str(cli["features"]),
            "--clean-data",
            str(cli["clean"]),
            "--scope",
            str(cli["scope"]),
            "--out-dir",
            str(cli["out"]),
            "--run-id",
            "r",
        ]
    )


def test_command_writes_all_outputs_and_reruns_identically(cli):
    assert run_cli(cli) == 0
    out = cli["out"]
    assert {p.name for p in out.iterdir()} == set(train.OUTPUT_FILES)
    first = {
        name: (out / name).read_bytes() for name in train.OUTPUT_FILES if name != train.MODEL_FILE
    }
    metrics = json.loads((out / train.METRICS_FILE).read_text())
    assert metrics["schema_version"] == train.SCHEMA_VERSION
    bundle = joblib.load(out / train.MODEL_FILE)
    assert bundle["selected_model"] == metrics["selected_model"]
    assert run_cli(cli) == 0
    for name, content in first.items():
        assert (out / name).read_bytes() == content


def test_outputs_contain_no_actual_sales(cli):
    assert run_cli(cli) == 0
    for name in (train.TEST_FORECAST_FILE, train.FORECAST_FILE):
        header = (cli["out"] / name).read_text().splitlines()[0]
        assert "units_sold" not in header and "actual" not in header


@pytest.mark.parametrize("breakage", ["no_features", "bad_scope", "bad_clean"])
def test_failed_run_removes_stale_outputs(cli, breakage):
    out = cli["out"]
    out.mkdir()
    for name in train.OUTPUT_FILES:
        (out / name).write_text("STALE")
        (out / f"{name}.tmp").write_text("STALE")
    if breakage == "no_features":
        cli["features"].unlink()
    elif breakage == "bad_scope":
        cli["scope"].write_text("{not json")
    else:
        cli["clean"].write_text("date,item_id\n2011-01-29,X\n")
    assert run_cli(cli) == 1
    assert list(out.iterdir()) == []


def test_default_outputs_are_ignored_by_git():
    if shutil.which("git") is None:
        pytest.skip("git not available")
    root = Path(__file__).resolve().parents[2]
    for name in train.OUTPUT_FILES:
        probe = subprocess.run(
            ["git", "check-ignore", "-q", str(train.DEFAULT_OUT_DIR / name)], cwd=root, check=False
        )
        if probe.returncode == 128:
            pytest.skip("not a git repository")
        assert probe.returncode == 0, name
