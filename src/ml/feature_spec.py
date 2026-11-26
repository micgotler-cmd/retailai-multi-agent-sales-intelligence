"""The feature schema: one source of truth for the Feature Engineer, Gate 2 and the Model Trainer.

The feature set is fixed (D-06, D-07). This module defines the columns, their kinds, the
look-back rules and the validation of `features.csv`, in plain Python (no schema framework,
T-12). Nothing else in the project lists feature names.

Leakage rule: a feature for target day t may use sales only from day t - 28 or earlier
(`MIN_LOOKBACK_DAYS`). Then every target in origin+1 .. origin+28 has all its features
computed from data at or before the origin, so no recursive forecasting is needed.
"""

from __future__ import annotations

import pandas as pd

from src.data.scope import DataScope
from src.ml.windows import final_test_window, future_window

SCHEMA_VERSION = "1.0.0"
MIN_LOOKBACK_DAYS = 28

KEY_COLUMNS = ["store_id", "item_id", "date"]
METADATA_COLUMNS = ["day", "demand_group"]  # reporting only, never model input
TARGET_COLUMN = "units_sold"

# Same-weekday lags (feature name -> days back) and rolling windows ending at t - 28
# (feature name -> (statistic, window length in days)).
LAG_FEATURES = {"lag_28": 28, "lag_35": 35, "lag_42": 42}
ROLLING_END_LAG = 28
ROLLING_FEATURES = {
    "roll_mean_7": ("mean", 7),
    "roll_mean_28": ("mean", 28),
    "roll_std_28": ("std", 28),
}
CALENDAR_FEATURES = ["day_of_week", "month", "day_of_month"]
KNOWN_IN_ADVANCE_FEATURES = ["snap", "store_closed"]
CATEGORICAL_FEATURES = ["item_id", "dept_id", "cat_id", "event_type_1"]

NUMERIC_FEATURES = (
    list(LAG_FEATURES) + list(ROLLING_FEATURES) + CALENDAR_FEATURES + KNOWN_IN_ADVANCE_FEATURES
)
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
# `item_id` is both the item's identity (a key) and a categorical model input.
ALL_COLUMNS = (
    KEY_COLUMNS
    + METADATA_COLUMNS
    + [TARGET_COLUMN]
    + [c for c in FEATURE_COLUMNS if c != "item_id"]
)
# Columns whose value comes from past sales and can be missing early in an item's history.
HISTORY_FEATURES = list(LAG_FEATURES) + list(ROLLING_FEATURES)


class FeatureError(Exception):
    """Raised when features cannot be built or `features.csv` breaks the schema."""


def longest_lookback() -> int:
    """Days back from the target day to the oldest sales value any feature reads."""
    lags = max(LAG_FEATURES.values())
    rolling = max(ROLLING_END_LAG + length - 1 for _, length in ROLLING_FEATURES.values())
    return max(lags, rolling)


def check_spec(horizon_days: int) -> None:
    """Fail if any feature could read sales newer than t - horizon (the leakage rule)."""
    if horizon_days > MIN_LOOKBACK_DAYS:
        raise FeatureError(
            f"The horizon ({horizon_days} days) is longer than the minimum look-back "
            f"({MIN_LOOKBACK_DAYS}); direct forecasting would leak"
        )
    too_short = {n: lag for n, lag in LAG_FEATURES.items() if lag < horizon_days}
    if too_short or ROLLING_END_LAG < horizon_days:
        raise FeatureError(f"Look-back shorter than the horizon: {too_short or 'rolling windows'}")
    overlap = set(FEATURE_COLUMNS) & (set(METADATA_COLUMNS) | {TARGET_COLUMN})
    if overlap:
        raise FeatureError(f"Features overlap with target or metadata: {sorted(overlap)}")


def validate_features(df: pd.DataFrame, scope: DataScope) -> None:
    """Check a features table against the schema (used by the builder and by Gate 2).

    Raises FeatureError for: wrong or missing columns, wrong kinds, duplicate item-days, an
    item that is missing, observed days (up to the last observed day) without a target,
    future days with a target, and any forecast-window day (test or future) that is absent
    or has an incomplete feature.
    """
    check_spec(scope.horizon_days)
    if list(df.columns) != ALL_COLUMNS:
        missing = [c for c in ALL_COLUMNS if c not in df.columns]
        extra = [c for c in df.columns if c not in ALL_COLUMNS]
        raise FeatureError(
            f"Feature columns differ from the schema: missing {missing}, extra {extra}"
        )
    _check_kinds(df)
    if df.duplicated(subset=["item_id", "date"]).any():
        raise FeatureError("Duplicate item-days in features")
    if set(df["item_id"]) != set(scope.item_ids):
        raise FeatureError("The items in features differ from the approved scope")
    observed = df["day"] <= scope.last_day
    if df.loc[observed, TARGET_COLUMN].isna().any():
        raise FeatureError("An observed day has no target")
    if df.loc[~observed, TARGET_COLUMN].notna().any():
        raise FeatureError("A future day carries a target (actual sales must not be there)")
    for window in (final_test_window(scope), future_window(scope)):
        _check_window_complete(df, window.name, window.first_day, window.last_day, scope)


def _check_kinds(df: pd.DataFrame) -> None:
    for column in NUMERIC_FEATURES + ["day", TARGET_COLUMN]:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise FeatureError(f"Column {column} must be numeric")
    for column in CATEGORICAL_FEATURES + ["store_id", "demand_group"]:
        if df[column].isna().any():
            raise FeatureError(f"Column {column} has missing values")
        if not all(isinstance(v, str) for v in df[column]):
            raise FeatureError(f"Column {column} must be text")
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        raise FeatureError("Column date must hold dates")


def _check_window_complete(
    df: pd.DataFrame, name: str, first_day: int, last_day: int, scope: DataScope
) -> None:
    rows = df[(df["day"] >= first_day) & (df["day"] <= last_day)]
    expected = (last_day - first_day + 1) * len(scope.item_ids)
    if len(rows) != expected:
        raise FeatureError(f"Window {name}: expected {expected} item-days, found {len(rows)}")
    if rows[FEATURE_COLUMNS].isna().any().any():
        bad = rows.loc[rows[FEATURE_COLUMNS].isna().any(axis=1), "item_id"].unique()
        raise FeatureError(f"Window {name}: incomplete features for item(s) {sorted(bad)}")
