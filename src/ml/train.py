"""Tune, compare, test and refit the forecasting models (P-08).

    uv run python -m src.ml.train

Reads `artifacts/ml/features.csv` (see `src.ml.features`) and `artifacts/clean/clean_data.csv`
(row-level M5 data, local only, T-04) and writes to `artifacts/ml/` (git-ignored) or `--out-dir`:
`metrics.json`, `test_forecast.csv`, `forecast.csv` and `model.joblib`. Fully deterministic;
no LLM calls.

Order of work (T-16, T-23):
1. Every candidate (4 Ridge alphas, 8 Random Forest settings) is fitted separately on each of
   the three backtest windows' own history and scored there. The primary selection metric is
   the mean overall MAE across those windows. The test window is not read at this stage.
2. The best setting per variant is kept; the variant with the lower metric is selected.
3. The selected setting is fitted on days up to d_1913 and scored once on the test window.
   The Seasonal Naive baseline is scored on the same window. Other candidates are never
   scored on the test window.
4. Both variants' chosen settings are refitted on all history up to d_1941 (same
   hyperparameters) and the selected one forecasts d_1942 to d_1969. Test metrics are not
   recomputed.

Outputs hold predictions only, no actual sales (T-04). A failed run leaves no outputs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
from pathlib import Path

import joblib
import pandas as pd
import sklearn

from src.data.cleaning import CleaningError, date_of_day, day_to_date
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope
from src.ml import evaluate_baseline as baseline_eval
from src.ml import feature_spec as spec
from src.ml import features as ft
from src.ml import models
from src.ml.baseline import HistoryError
from src.ml.evaluate_baseline import DEFAULT_CLEAN_DATA, EvaluationError
from src.ml.feature_spec import FeatureError
from src.ml.metrics import MetricsError, mean_of_windows, score_forecast
from src.ml.models import Candidate, ModelError
from src.ml.windows import (
    ForecastWindow,
    WindowError,
    backtest_windows,
    final_test_window,
    future_window,
)
from src.utils.logging_setup import setup_from_env

logger = logging.getLogger(__name__)

DEFAULT_FEATURES = Path("artifacts/ml/features.csv")
DEFAULT_OUT_DIR = Path("artifacts/ml")
METRICS_FILE = "metrics.json"
TEST_FORECAST_FILE = "test_forecast.csv"
FORECAST_FILE = "forecast.csv"
MODEL_FILE = "model.joblib"
OUTPUT_FILES = (METRICS_FILE, TEST_FORECAST_FILE, FORECAST_FILE, MODEL_FILE)
SCHEMA_VERSION = "2.0.0"
BUNDLE_VERSION = "1.0.0"
SELECTION_METRIC = "mean overall MAE across the three backtest windows"
TEST_FORECAST_COLUMNS = [
    "run_id",
    "store_id",
    "item_id",
    "forecast_date",
    "model",
    "predicted_units",
]
# The future forecast also carries model_version (documented interface, database design).
FORECAST_COLUMNS = [
    "run_id",
    "store_id",
    "item_id",
    "forecast_date",
    "model",
    "predicted_units",
    "model_version",
]


def model_version(variant: str, fitted_through_day: int, run_id: str) -> str:
    """Identifies the fitted model behind a future forecast: variant, last training day, run.

    Example: `ridge-d1941-20261126-171500-a1b2c3`. The model is the pipeline stored for that
    variant in the run's `model.joblib`, refitted on all history up to that day with the
    hyperparameters recorded in `metrics.json`.
    """
    return f"{variant}-d{fitted_through_day}-{run_id}"


def run(
    features: pd.DataFrame, clean: pd.DataFrame, scope: DataScope, run_id: str
) -> tuple[dict, pd.DataFrame, pd.DataFrame, dict]:
    """Run the whole pipeline; return (metrics, test forecast, future forecast, model bundle)."""
    spec.validate_features(features, scope)
    day_1 = day_to_date(clean, scope)
    baseline_metrics, _ = baseline_eval.evaluate(clean, scope, run_id)

    tuning = [_tune(c, features, clean, scope, day_1) for c in models.candidates()]
    best = _best_per_variant(tuning)
    selected = _select(best)
    chosen = best[selected]["candidate"]
    logger.info("Selected %s %s (backtest MAE %.4f)", selected, chosen.params, _mae(best[selected]))

    test_window = final_test_window(scope)
    test_origin = test_window.origin_day
    test_model = models.fit(chosen, ft.training_rows(features, test_origin))
    test_forecast = _forecast(test_model, features, test_window)
    test_scores = score_forecast(test_forecast, _actual(clean, day_1, test_window), scope.items)
    test_entry = _window_entry(day_1, test_window, test_scores)

    final_fits = {
        variant: models.fit(info["candidate"], ft.training_rows(features, scope.last_day))
        for variant, info in best.items()
    }
    future = _forecast(final_fits[selected], features, future_window(scope))

    metrics = _metrics_document(
        scope, run_id, tuning, best, selected, baseline_metrics, test_entry, day_1
    )
    bundle = _bundle(run_id, scope, best, selected, final_fits)
    version = model_version(selected, scope.last_day, run_id)
    metrics["refit"]["model_version"] = version
    bundle["model_version"] = version
    future_table = _with_labels(future, run_id, selected, TEST_FORECAST_COLUMNS).assign(
        model_version=version
    )[FORECAST_COLUMNS]
    return (
        metrics,
        _with_labels(test_forecast, run_id, selected, TEST_FORECAST_COLUMNS),
        future_table,
        bundle,
    )


def _tune(candidate: Candidate, features: pd.DataFrame, clean: pd.DataFrame, scope, day_1) -> dict:
    """Fit the candidate on each backtest window's history and score it there (only)."""
    entries = []
    for window in backtest_windows(scope):
        model = models.fit(candidate, ft.training_rows(features, window.origin_day))
        forecast = _forecast(model, features, window)
        scores = score_forecast(forecast, _actual(clean, day_1, window), scope.items)
        entries.append(_window_entry(day_1, window, scores))
    return {"candidate": candidate, "windows": entries, "mean_overall": mean_of_windows(entries)}


def _best_per_variant(tuning: list[dict]) -> dict[str, dict]:
    """Lowest mean backtest MAE per variant; the first grid point wins a tie."""
    best: dict[str, dict] = {}
    for result in tuning:
        variant = result["candidate"].variant
        if variant not in best or _mae(result) < _mae(best[variant]):
            best[variant] = result
    return best


def _select(best: dict[str, dict]) -> str:
    """The variant with the lowest mean backtest MAE; the earlier variant wins a tie."""
    return min(models.VARIANTS, key=lambda v: _mae(best[v]))


def _mae(result: dict) -> float:
    return result["mean_overall"]["mae"]


def _forecast(pipeline, features: pd.DataFrame, window: ForecastWindow) -> pd.DataFrame:
    rows = ft.forecast_rows(features, window)
    out = rows[["store_id", "item_id", "date"]].rename(columns={"date": "forecast_date"})
    out["predicted_units"] = models.predict_units(pipeline, rows)
    return out.sort_values(["item_id", "forecast_date"]).reset_index(drop=True)


def _actual(clean: pd.DataFrame, day_1: pd.Timestamp, window: ForecastWindow) -> pd.DataFrame:
    first, last = date_of_day(day_1, window.first_day), date_of_day(day_1, window.last_day)
    return clean[(clean["date"] >= first) & (clean["date"] <= last)]


def _window_entry(day_1: pd.Timestamp, window: ForecastWindow, scores: dict) -> dict:
    origin = date_of_day(day_1, window.origin_day)
    first, last = date_of_day(day_1, window.first_day), date_of_day(day_1, window.last_day)
    return {
        "window": window.name,
        "origin_day": window.origin_day,
        "origin_date": origin.date().isoformat(),
        "first_day": window.first_day,
        "last_day": window.last_day,
        "first_date": first.date().isoformat(),
        "last_date": last.date().isoformat(),
        **scores,
    }


def _with_labels(
    forecast: pd.DataFrame, run_id: str, model: str, columns: list[str]
) -> pd.DataFrame:
    return forecast.assign(run_id=run_id, model=model)[columns]


def _grid_description() -> dict:
    return {variant: models.GRIDS[variant] for variant in models.VARIANTS}


def _metrics_document(
    scope, run_id, tuning, best, selected, baseline_metrics, test_entry, day_1
) -> dict:
    baseline_mean = baseline_metrics["backtest"]["mean_overall"]
    chosen = best[selected]
    test_mae = test_entry["overall"]["mae"]
    baseline_test = baseline_metrics["test"]["overall"]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "store_id": scope.store_id,
        "n_items": len(scope.item_ids),
        "horizon_days": scope.horizon_days,
        "selected_model": selected,
        "selection": {
            "metric": SELECTION_METRIC,
            "data": "the three rolling-origin backtest windows only (T-23); the test window is not read",
            "tie_break": "first grid point, then ridge before random_forest",
            "seed": models.SEED,
            "grids": _grid_description(),
            "n_candidates": len(tuning),
            "selected_hyperparameters": chosen["candidate"].params,
            "selected_mean_backtest_mae": _mae(chosen),
            "baseline_mean_backtest_mae": baseline_mean["mae"],
            "beats_baseline_on_backtest": _mae(chosen) < baseline_mean["mae"],
        },
        "definitions": {
            "mae": "mean absolute error over item-days",
            "rmse": "root mean squared error over item-days",
            "pooling": "overall and per demand group pool all item-days; per_item is separate",
            "clipping": "predictions are clipped at 0 in backtests, the test forecast and the "
            "future forecast alike",
            "baseline": baseline_metrics["definitions"]["baseline"],
        },
        "models": {
            "seasonal_naive": {"backtest": baseline_metrics["backtest"]},
            **{
                variant: {
                    "hyperparameters": best[variant]["candidate"].params,
                    "backtest": {
                        "purpose": "model comparison and tuning only (T-23)",
                        "windows": best[variant]["windows"],
                        "mean_overall": best[variant]["mean_overall"],
                    },
                }
                for variant in models.VARIANTS
            },
        },
        "backtest_candidates": [
            {
                "model": r["candidate"].variant,
                "hyperparameters": r["candidate"].params,
                "mean_overall": r["mean_overall"],
            }
            for r in tuning
        ],
        "test": {
            "purpose": "final evaluation, scored once (T-09, T-16)",
            "model": selected,
            "hyperparameters": chosen["candidate"].params,
            "fitted_through_day": test_entry["origin_day"],
            **test_entry,
            "seasonal_naive": baseline_metrics["test"],
            "improvement_over_baseline_mae": round(baseline_test["mae"] - test_mae, 6),
        },
        "refit": {
            "fitted_through_day": scope.last_day,
            "note": "the selected model type is refitted with the same hyperparameters on all "
            "history up to the last observed day for forecast.csv; test metrics are not "
            "recomputed (T-16)",
        },
        "notes": [
            "Only the selected model and the baseline are scored on the test window.",
            "Outputs hold no actual sales values (T-04); forecasts are predictions only.",
        ],
    }


def _bundle(run_id: str, scope: DataScope, best: dict, selected: str, fits: dict) -> dict:
    """Both variants with their fitted preprocessing, refitted on all history (M-04)."""
    return {
        "bundle_version": BUNDLE_VERSION,
        "run_id": run_id,
        "selected_model": selected,
        "fitted_through_day": scope.last_day,
        "feature_schema_version": spec.SCHEMA_VERSION,
        "feature_columns": spec.FEATURE_COLUMNS,
        "seed": models.SEED,
        "library_versions": {
            "scikit-learn": sklearn.__version__,
            "python": platform.python_version(),
        },
        "variants": {
            variant: {
                "hyperparameters": best[variant]["candidate"].params,
                "pipeline": fits[variant],
            }
            for variant in models.VARIANTS
        },
    }


def clear_outputs(out_dir: Path) -> None:
    """Remove outputs of earlier runs (and leftover temp files) so a failure leaves none."""
    for name in OUTPUT_FILES:
        for path in (out_dir / name, out_dir / f"{name}.tmp"):
            path.unlink(missing_ok=True)


def write_outputs(
    metrics: dict, test_forecast: pd.DataFrame, forecast: pd.DataFrame, bundle: dict, out_dir: Path
) -> list[Path]:
    """Write all four files via temp files; the folder never holds a half-written result."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / name for name in OUTPUT_FILES}
    tmps = {name: path.with_name(path.name + ".tmp") for name, path in paths.items()}
    try:
        tmps[METRICS_FILE].write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        test_forecast.to_csv(tmps[TEST_FORECAST_FILE], index=False, date_format="%Y-%m-%d")
        forecast.to_csv(tmps[FORECAST_FILE], index=False, date_format="%Y-%m-%d")
        joblib.dump(bundle, tmps[MODEL_FILE])
        for name in OUTPUT_FILES:
            os.replace(tmps[name], paths[name])
    except OSError:
        clear_outputs(out_dir)
        raise
    return list(paths.values())


def main(argv: list[str] | None = None) -> int:
    """Train and evaluate; exit code 1 (and no outputs) on any problem."""
    setup_from_env()
    parser = argparse.ArgumentParser(description="Tune, test and refit Ridge and Random Forest.")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--clean-data", type=Path, default=DEFAULT_CLEAN_DATA)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default="standalone")
    args = parser.parse_args(argv)
    try:
        clear_outputs(args.out_dir)
        scope = load_scope(args.scope)
        clean = baseline_eval.load_clean_data(args.clean_data)
        features = ft.read_features(args.features)
        metrics, test_forecast, forecast, bundle = run(features, clean, scope, args.run_id)
        paths = write_outputs(metrics, test_forecast, forecast, bundle, args.out_dir)
    except (
        ScopeError,
        EvaluationError,
        CleaningError,
        HistoryError,
        MetricsError,
        WindowError,
        FeatureError,
        ModelError,
        OSError,
    ) as exc:
        clear_outputs(args.out_dir)
        logger.error("%s", exc)
        return 1
    for path in paths:
        logger.info("Wrote %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
