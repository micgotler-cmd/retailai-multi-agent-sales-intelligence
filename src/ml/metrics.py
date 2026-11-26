"""MAE and RMSE for forecasts (D-04): overall, per item and per demand group.

MAPE is not used because intermittent items contain many zeros. "Overall" and
"per demand group" pool every item-day in the group (not an average of item
scores), so busy items weigh more, as in the data itself; per-item scores are
reported separately so no group hides a weak item.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FORECAST_KEYS = ["item_id", "forecast_date"]
DECIMALS = 6


class MetricsError(Exception):
    """Raised when forecast and actual values cannot be compared safely."""


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean absolute error."""
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root mean squared error."""
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def score_forecast(
    forecast: pd.DataFrame, actual: pd.DataFrame, demand_groups: dict[str, str]
) -> dict:
    """Compare a forecast with the observed values for exactly the same item-days.

    `forecast` needs item_id, forecast_date, predicted_units; `actual` needs item_id,
    date, units_sold; `demand_groups` maps item_id to high, medium or low. Raises
    MetricsError for duplicate keys, differing item-days, unknown items or non-finite values.
    """
    joined = _align(forecast, actual, demand_groups)
    actual_values = joined["units_sold"].to_numpy(dtype=float)
    predicted = joined["predicted_units"].to_numpy(dtype=float)
    result = {
        "n_item_days": len(joined),
        "overall": _pair(actual_values, predicted),
        "per_item": {},
        "per_demand_group": {},
    }
    for item_id, rows in joined.groupby("item_id", sort=True):
        result["per_item"][item_id] = _pair(
            rows["units_sold"].to_numpy(float), rows["predicted_units"].to_numpy(float)
        ) | {"demand_group": demand_groups[item_id], "n_item_days": len(rows)}
    for group in ("high", "medium", "low"):
        rows = joined[joined["demand_group"] == group]
        if rows.empty:
            continue
        result["per_demand_group"][group] = _pair(
            rows["units_sold"].to_numpy(float), rows["predicted_units"].to_numpy(float)
        ) | {"n_items": int(rows["item_id"].nunique()), "n_item_days": len(rows)}
    return result


def mean_of_windows(window_scores: list[dict]) -> dict:
    """Average the overall MAE and RMSE across backtest windows (each window counts once)."""
    if not window_scores:
        raise MetricsError("No windows to average")
    return {
        "mae": round(float(np.mean([w["overall"]["mae"] for w in window_scores])), DECIMALS),
        "rmse": round(float(np.mean([w["overall"]["rmse"] for w in window_scores])), DECIMALS),
    }


def _pair(actual: np.ndarray, predicted: np.ndarray) -> dict:
    return {
        "mae": round(mae(actual, predicted), DECIMALS),
        "rmse": round(rmse(actual, predicted), DECIMALS),
    }


def _align(forecast: pd.DataFrame, actual: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    for frame, columns, label in (
        (forecast, FORECAST_KEYS + ["predicted_units"], "forecast"),
        (actual, ["item_id", "date", "units_sold"], "actual"),
    ):
        missing = [c for c in columns if c not in frame.columns]
        if missing:
            raise MetricsError(f"The {label} table is missing columns: {missing}")
    left = forecast[FORECAST_KEYS + ["predicted_units"]]
    right = actual[["item_id", "date", "units_sold"]].rename(columns={"date": "forecast_date"})
    for frame, label in ((left, "forecast"), (right, "actual")):
        if frame.duplicated(subset=FORECAST_KEYS).any():
            raise MetricsError(f"The {label} table has duplicate item-days")
    joined = left.merge(right, on=FORECAST_KEYS, how="outer", indicator=True)
    if (joined["_merge"] != "both").any():
        n_missing_actual = int((joined["_merge"] == "left_only").sum())
        n_missing_forecast = int((joined["_merge"] == "right_only").sum())
        raise MetricsError(
            f"Forecast and actual cover different item-days: {n_missing_actual} forecast "
            f"row(s) without an actual, {n_missing_forecast} actual row(s) without a forecast"
        )
    unknown = sorted(set(joined["item_id"]) - set(groups))
    if unknown:
        raise MetricsError(f"Items without a demand group: {unknown}")
    for column in ("predicted_units", "units_sold"):
        if not np.isfinite(pd.to_numeric(joined[column], errors="coerce")).all():
            raise MetricsError(f"Column {column} has missing or non-finite values")
    if joined.empty:
        raise MetricsError("Nothing to score: no item-days")
    joined["demand_group"] = joined["item_id"].map(groups)
    return joined.drop(columns="_merge")
