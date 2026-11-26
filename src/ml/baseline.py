"""Seasonal Naive baseline (D-04, T-23).

For one forecast origin it takes the last seven observed daily values and
repeats that week to fill the horizon: day origin+1 gets the value of origin-6,
day origin+2 the value of origin-5, and so on, so every weekday gets its own
last observed value (4 repeats for 28 days). Only rows up to and including the
origin are read; nothing inside the forecast window can influence the result.

A zero-sales day is a valid observation. A missing day, a missing value or a
negative value inside the last seven days is an error, never padded or imputed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MODEL_NAME = "seasonal_naive"
SEASON_DAYS = 7
REQUIRED_COLUMNS = ("store_id", "item_id", "date", "units_sold")
FORECAST_COLUMNS = ["store_id", "item_id", "forecast_date", "predicted_units"]


class HistoryError(Exception):
    """Raised when an item lacks enough valid observed history before an origin."""


def consecutive_valid_days(item_rows: pd.DataFrame, origin: pd.Timestamp) -> int:
    """Count consecutive calendar days with a valid observation, ending at the origin.

    A day is valid when its row exists and `units_sold` is a finite number >= 0.
    Zero is valid. Rows after the origin are ignored.
    """
    known = item_rows[item_rows["date"] <= origin]
    units = pd.to_numeric(known["units_sold"], errors="coerce")
    valid = known.loc[np.isfinite(units) & (units >= 0), "date"]
    valid_dates = set(valid)
    count = 0
    day = origin
    while day in valid_dates:
        count += 1
        day -= pd.Timedelta(days=1)
    return count


def seasonal_naive(
    history: pd.DataFrame,
    origin: pd.Timestamp,
    horizon: int,
    item_ids: list[str],
) -> pd.DataFrame:
    """Forecast `horizon` days after `origin` for every item in `item_ids`.

    Raises HistoryError (naming the item, the origin and the available history) if an
    item has fewer than seven consecutive valid days ending at the origin, or if its
    rows are duplicated or mix stores. Nothing is padded, imputed, skipped or replaced.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in history.columns]
    if missing:
        raise HistoryError(f"History is missing columns: {missing}")
    if horizon < 1:
        raise HistoryError("horizon must be at least 1 day")
    origin = pd.Timestamp(origin)
    known = history[history["date"] <= origin]  # the only rows the forecast may read
    parts = []
    for item_id in item_ids:
        rows = known[known["item_id"] == item_id]
        parts.append(_forecast_item(rows, item_id, origin, horizon))
    return pd.concat(parts, ignore_index=True)[FORECAST_COLUMNS]


def _forecast_item(rows: pd.DataFrame, item_id: str, origin: pd.Timestamp, horizon: int):
    if rows["date"].duplicated().any():
        raise HistoryError(f"Item {item_id}: duplicate dates before origin {origin.date()}")
    available = consecutive_valid_days(rows, origin)
    if available < SEASON_DAYS:
        raise HistoryError(
            f"Item {item_id}: forecast origin {origin.date()} has {available} consecutive valid "
            f"observed day(s) of history; at least {SEASON_DAYS} are required"
        )
    stores = rows["store_id"].unique()
    if len(stores) != 1:
        raise HistoryError(f"Item {item_id}: expected exactly one store, found {len(stores)}")
    window = rows[rows["date"] > origin - pd.Timedelta(days=SEASON_DAYS)]
    last_week = window.sort_values("date")["units_sold"].to_numpy(dtype=float)
    steps = np.arange(horizon)
    return pd.DataFrame(
        {
            "store_id": stores[0],
            "item_id": item_id,
            "forecast_date": origin + pd.to_timedelta(steps + 1, unit="D"),
            "predicted_units": last_week[steps % SEASON_DAYS],
        }
    )
