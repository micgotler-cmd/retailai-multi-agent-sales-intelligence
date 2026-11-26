"""Run the Seasonal Naive baseline on the backtest windows and the test window (P-08).

    uv run python -m src.ml.evaluate_baseline

Reads `artifacts/clean/clean_data.csv` (row-level M5 data, local only, T-04) and the
approved scope, and writes `metrics.json` and `test_forecast.csv` to the output
folder (default `artifacts/ml/`, git-ignored; the Crew 2 runner will pass its own
run folder). The baseline has no fitted parameters, so the test window is scored once
and nothing is tuned on it. The outputs carry no actual sales values.

A failed run never leaves outputs behind: the previous outputs are removed first and
the new ones are written only after every check has passed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import pandas as pd

from src.data.cleaning import CleaningError, date_of_day, day_to_date
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope
from src.ml import baseline
from src.ml.baseline import HistoryError
from src.ml.metrics import MetricsError, mean_of_windows, score_forecast
from src.ml.windows import ForecastWindow, WindowError, backtest_windows, final_test_window
from src.utils.logging_setup import setup_from_env

logger = logging.getLogger(__name__)

DEFAULT_CLEAN_DATA = Path("artifacts/clean/clean_data.csv")
DEFAULT_OUT_DIR = Path("artifacts/ml")
METRICS_FILE = "metrics.json"
TEST_FORECAST_FILE = "test_forecast.csv"
SCHEMA_VERSION = "1.0.0"
REQUIRED_COLUMNS = ("store_id", "item_id", "date", "units_sold")


class EvaluationError(Exception):
    """Raised when the clean data cannot be evaluated against the approved scope."""


def load_clean_data(path: Path) -> pd.DataFrame:
    """Read clean_data.csv with real dates; raise EvaluationError if it is unusable."""
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except FileNotFoundError as exc:
        raise EvaluationError(f"Clean data not found: {path} (run src.data.cleaning)") from exc
    except (ValueError, KeyError) as exc:
        raise EvaluationError(f"Clean data could not be read: {path} ({exc})") from exc
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise EvaluationError(f"Clean data is missing columns: {missing}")
    return df


def evaluate(clean: pd.DataFrame, scope: DataScope, run_id: str) -> tuple[dict, pd.DataFrame]:
    """Score the baseline on every backtest window and once on the test window.

    Returns the metrics document and the test forecast table. Raises EvaluationError,
    HistoryError, MetricsError, WindowError or CleaningError on any problem.
    """
    unknown = set(clean["item_id"]) - set(scope.item_ids)
    absent = set(scope.item_ids) - set(clean["item_id"])
    if unknown or absent:
        raise EvaluationError(
            f"Clean data and scope disagree: items not in scope {sorted(unknown)}, "
            f"scope items without data {sorted(absent)}"
        )
    day_1 = day_to_date(clean, scope)
    backtest = [_score_window(clean, scope, day_1, w) for w in backtest_windows(scope)]
    test_scores, test_forecast = _score_window(clean, scope, day_1, final_test_window(scope))
    test_forecast = test_forecast.assign(run_id=run_id, model=baseline.MODEL_NAME)[
        ["run_id", "store_id", "item_id", "forecast_date", "model", "predicted_units"]
    ]
    metrics = {
        "schema_version": SCHEMA_VERSION,
        "model": baseline.MODEL_NAME,
        "run_id": run_id,
        "store_id": scope.store_id,
        "n_items": len(scope.item_ids),
        "horizon_days": scope.horizon_days,
        "definitions": {
            "mae": "mean absolute error over item-days",
            "rmse": "root mean squared error over item-days",
            "pooling": "overall and per demand group pool all item-days; per_item is separate",
            "baseline": "last 7 observed daily values before the origin, repeated 4 times (T-23)",
        },
        "backtest": {
            "purpose": "model comparison and tuning only (T-23)",
            "windows": [entry for entry, _ in backtest],
            "mean_overall": mean_of_windows([entry for entry, _ in backtest]),
        },
        "test": test_scores,
        "notes": [
            "The baseline has no fitted parameters; the test window is scored once, untouched.",
            "Outputs hold no actual sales values (T-04); test_forecast.csv has predictions only.",
        ],
    }
    return metrics, test_forecast


def _score_window(
    clean: pd.DataFrame,
    scope: DataScope,
    day_1: pd.Timestamp,
    window: ForecastWindow,
) -> tuple[dict, pd.DataFrame]:
    """Forecast one window from its own origin and score it; return (score entry, forecast)."""
    origin = date_of_day(day_1, window.origin_day)
    first = date_of_day(day_1, window.first_day)
    last = date_of_day(day_1, window.last_day)
    history = clean[clean["date"] <= origin]  # nothing later is ever passed to the baseline
    forecast = baseline.seasonal_naive(history, origin, window.n_days, scope.item_ids)
    actual = clean[(clean["date"] >= first) & (clean["date"] <= last)]
    scores = score_forecast(forecast, actual, scope.items)
    entry = {
        "window": window.name,
        "origin_day": window.origin_day,
        "origin_date": origin.date().isoformat(),
        "first_day": window.first_day,
        "last_day": window.last_day,
        "first_date": first.date().isoformat(),
        "last_date": last.date().isoformat(),
        **scores,
    }
    logger.info(
        "%s (origin %s): overall MAE %.4f, RMSE %.4f",
        window.name,
        entry["origin_date"],
        scores["overall"]["mae"],
        scores["overall"]["rmse"],
    )
    return entry, forecast


def clear_outputs(out_dir: Path) -> None:
    """Remove outputs of earlier runs (and leftover temp files) so a failure leaves none."""
    for name in (METRICS_FILE, TEST_FORECAST_FILE):
        for path in (out_dir / name, out_dir / f"{name}.tmp"):
            path.unlink(missing_ok=True)


def write_outputs(metrics: dict, test_forecast: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Write both files via temp files, so the folder never holds a half-written result."""
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path, forecast_path = out_dir / METRICS_FILE, out_dir / TEST_FORECAST_FILE
    metrics_tmp = metrics_path.with_name(metrics_path.name + ".tmp")
    forecast_tmp = forecast_path.with_name(forecast_path.name + ".tmp")
    try:
        metrics_tmp.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        test_forecast.to_csv(forecast_tmp, index=False, date_format="%Y-%m-%d")
        os.replace(metrics_tmp, metrics_path)
        os.replace(forecast_tmp, forecast_path)
    except OSError:
        clear_outputs(out_dir)
        raise
    return [metrics_path, forecast_path]


def main(argv: list[str] | None = None) -> int:
    """Evaluate the baseline; exit code 1 (and no outputs) on any problem."""
    setup_from_env()
    parser = argparse.ArgumentParser(description="Seasonal Naive baseline: backtest and test.")
    parser.add_argument("--clean-data", type=Path, default=DEFAULT_CLEAN_DATA)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default="standalone")
    args = parser.parse_args(argv)
    try:
        clear_outputs(args.out_dir)
        scope = load_scope(args.scope)
        metrics, test_forecast = evaluate(load_clean_data(args.clean_data), scope, args.run_id)
        paths = write_outputs(metrics, test_forecast, args.out_dir)
    except (
        ScopeError,
        EvaluationError,
        CleaningError,
        HistoryError,
        MetricsError,
        WindowError,
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
