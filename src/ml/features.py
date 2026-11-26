"""Build `features.csv` for all items, past and future (P-07).

    uv run python -m src.ml.features

Reads `artifacts/clean/clean_data.csv` and `data/raw/calendar.csv` (local only, T-04) and
the approved scope. One table covers every item from its first sale to the end of the
future window (d_1942 to d_1969). Observed days carry the target; future days leave it
empty. Features follow the schema in `feature_spec.py`: lags and rolling statistics read
only sales from day t - 28 or earlier, calendar, event and SNAP values come from the
calendar, `store_closed` follows the 25 December rule (T-13), and `sell_price` is not used
(D-07).

Missing history is never imputed: a feature whose look-back reaches before the item's
first sale is empty, and `training_rows` leaves those days out. A gap, a missing value or a
negative value inside an item's history is an error. A failed run leaves no output.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.cleaning import CLOSURE_MONTH_DAY, CleaningError, date_of_day, day_to_date
from src.data.etl import M5DataError, load_calendar_for_state
from src.data.m5_files import day_number
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope
from src.ml import feature_spec as spec
from src.ml.feature_spec import FeatureError
from src.ml.windows import ForecastWindow, WindowError, future_window
from src.utils.logging_setup import setup_from_env

logger = logging.getLogger(__name__)

DEFAULT_CLEAN_DATA = Path("artifacts/clean/clean_data.csv")
DEFAULT_CALENDAR = Path("data/raw/calendar.csv")
DEFAULT_OUT_DIR = Path("artifacts/ml")
FEATURES_FILE = "features.csv"
CLEAN_COLUMNS = ("store_id", "item_id", "dept_id", "cat_id", "state_id", "date", "units_sold")
NO_EVENT = "none"


def load_clean(path: Path) -> pd.DataFrame:
    """Read clean_data.csv with real dates; raise FeatureError if it is unusable."""
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except FileNotFoundError as exc:
        raise FeatureError(f"Clean data not found: {path} (run src.data.cleaning)") from exc
    except (ValueError, KeyError) as exc:
        raise FeatureError(f"Clean data could not be read: {path} ({exc})") from exc
    missing = [c for c in CLEAN_COLUMNS if c not in df.columns]
    if missing:
        raise FeatureError(f"Clean data is missing columns: {missing}")
    return df


def load_calendar(path: Path, state_id: str) -> pd.DataFrame:
    """Calendar with day number, event type and the SNAP flag of the store's state."""
    try:
        cal = load_calendar_for_state(path, state_id)
    except (FileNotFoundError, M5DataError, ValueError) as exc:
        raise FeatureError(f"Calendar could not be read: {path} ({exc})") from exc
    cal["day"] = cal["d"].map(day_number)
    return cal


def build_features(clean: pd.DataFrame, calendar: pd.DataFrame, scope: DataScope) -> pd.DataFrame:
    """Build the full features table (observed and future days) for every scoped item."""
    spec.check_spec(scope.horizon_days)
    _check_clean(clean, scope)
    try:
        day_1 = day_to_date(clean, scope)
    except CleaningError as exc:
        raise FeatureError(str(exc)) from exc
    last_day = future_window(scope).last_day
    cal = _calendar_by_date(calendar, day_1, last_day)
    parts = [
        _item_features(clean[clean["item_id"] == item_id], item_id, scope, day_1, last_day)
        for item_id in scope.item_ids
    ]
    table = pd.concat(parts, ignore_index=True)
    table["event_type_1"] = table["date"].map(cal["event_type_1"])
    table["snap"] = table["date"].map(cal["snap"]).astype(int)
    table["store_closed"] = _is_closure(table["date"]).astype(int)
    table["day_of_week"] = table["date"].dt.day_of_week
    table["month"] = table["date"].dt.month
    table["day_of_month"] = table["date"].dt.day
    table["demand_group"] = table["item_id"].map(scope.items)
    table["store_id"] = scope.store_id
    table["day"] = (table["date"] - day_1).dt.days + 1
    table = table[spec.ALL_COLUMNS].sort_values(["item_id", "date"]).reset_index(drop=True)
    spec.validate_features(table, scope)
    return table


def training_rows(features: pd.DataFrame, origin_day: int) -> pd.DataFrame:
    """Rows a model may train on at `origin_day`: target known, features complete.

    Targets after the origin are never included. Days whose look-back reaches before an
    item's first sale are left out (no imputation).
    """
    rows = features[features["day"] <= origin_day]
    rows = rows[rows[spec.TARGET_COLUMN].notna() & rows[spec.FEATURE_COLUMNS].notna().all(axis=1)]
    return rows.reset_index(drop=True)


def forecast_rows(features: pd.DataFrame, window: ForecastWindow) -> pd.DataFrame:
    """Feature rows for a forecast window, without the target column.

    Raises FeatureError unless every item has all of the window's days with complete features.
    """
    rows = features[(features["day"] >= window.first_day) & (features["day"] <= window.last_day)]
    n_items = features["item_id"].nunique()
    if len(rows) != window.n_days * n_items:
        raise FeatureError(f"Window {window.name}: features do not cover every item-day")
    if rows[spec.FEATURE_COLUMNS].isna().any().any():
        raise FeatureError(f"Window {window.name}: some features are incomplete")
    return rows.drop(columns=spec.TARGET_COLUMN).reset_index(drop=True)


def _check_clean(clean: pd.DataFrame, scope: DataScope) -> None:
    unknown = set(clean["item_id"]) - set(scope.item_ids)
    absent = set(scope.item_ids) - set(clean["item_id"])
    if unknown or absent:
        raise FeatureError(
            f"Clean data and scope disagree: items not in scope {sorted(unknown)}, "
            f"scope items without data {sorted(absent)}"
        )
    if clean["state_id"].nunique() != 1 or clean["store_id"].nunique() != 1:
        raise FeatureError("Clean data must hold exactly one store and one state")
    if clean["store_id"].iloc[0] != scope.store_id:
        raise FeatureError(f"Clean data store differs from the scope store {scope.store_id}")


def _calendar_by_date(calendar: pd.DataFrame, day_1: pd.Timestamp, last_day: int) -> pd.DataFrame:
    """Event type and SNAP flag per date; the calendar must cover d_1 .. last_day."""
    if calendar["date"].duplicated().any():
        raise FeatureError("Calendar has duplicate dates")
    cal = calendar.set_index("date")
    wanted = pd.date_range(day_1, date_of_day(day_1, last_day))
    if not wanted.isin(cal.index).all():
        raise FeatureError(f"Calendar does not cover d_1 to d_{last_day}")
    if (cal.loc[wanted, "day"].to_numpy() != np.arange(1, last_day + 1)).any():
        raise FeatureError("Calendar day numbers do not match the clean data's d_1 date")
    cal = cal.loc[wanted]
    if cal["snap"].isna().any() or not cal["snap"].isin([0, 1]).all():
        raise FeatureError("Calendar SNAP flag must be 0 or 1")
    return cal.assign(event_type_1=cal["event_type_1"].fillna(NO_EVENT).astype(str))


def _is_closure(dates: pd.Series) -> pd.Series:
    month, day = CLOSURE_MONTH_DAY
    return (dates.dt.month == month) & (dates.dt.day == day)


def _item_features(
    rows: pd.DataFrame, item_id: str, scope: DataScope, day_1: pd.Timestamp, last_day: int
) -> pd.DataFrame:
    """Target, descriptors and sales-based features for one item over its whole date range."""
    last_observed = date_of_day(day_1, scope.last_day)
    units = pd.to_numeric(rows["units_sold"], errors="coerce")
    if rows["date"].duplicated().any():
        raise FeatureError(f"Item {item_id}: duplicate dates")
    if not np.isfinite(units).all() or (units < 0).any():
        raise FeatureError(f"Item {item_id}: missing, non-finite or negative units_sold")
    first, last = rows["date"].min(), rows["date"].max()
    if last != last_observed:
        raise FeatureError(
            f"Item {item_id}: history ends {last.date()}, expected {last_observed.date()}"
        )
    if (last - first).days + 1 != len(rows):
        raise FeatureError(f"Item {item_id}: missing dates inside its history")
    for column in ("dept_id", "cat_id"):
        if rows[column].nunique() != 1:
            raise FeatureError(f"Item {item_id}: {column} is not unique")
    index = pd.date_range(first, date_of_day(day_1, last_day))
    sales = pd.Series(units.to_numpy(float), index=rows["date"]).reindex(index)
    frame = pd.DataFrame({"date": index, "item_id": item_id, spec.TARGET_COLUMN: sales.to_numpy()})
    for name, lag in spec.LAG_FEATURES.items():
        frame[name] = sales.shift(lag).to_numpy()
    past = sales.shift(spec.ROLLING_END_LAG)
    for name, (statistic, length) in spec.ROLLING_FEATURES.items():
        window = past.rolling(length, min_periods=length)
        frame[name] = (window.mean() if statistic == "mean" else window.std(ddof=0)).to_numpy()
    frame["dept_id"] = rows["dept_id"].iloc[0]
    frame["cat_id"] = rows["cat_id"].iloc[0]
    return frame


def read_features(path: Path) -> pd.DataFrame:
    """Read features.csv back with dates parsed (for Gate 2 and the Model Trainer)."""
    try:
        return pd.read_csv(path, parse_dates=["date"], keep_default_na=False, na_values=[""])
    except (FileNotFoundError, ValueError) as exc:
        raise FeatureError(f"Features could not be read: {path} ({exc})") from exc


def write_features(features: pd.DataFrame, out_dir: Path) -> Path:
    """Write features.csv via a temp file, so the folder never holds a half-written result."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FEATURES_FILE
    tmp = path.with_name(path.name + ".tmp")
    try:
        features.to_csv(tmp, index=False, date_format="%Y-%m-%d")
        os.replace(tmp, path)
    except OSError:
        clear_outputs(out_dir)
        raise
    return path


def clear_outputs(out_dir: Path) -> None:
    """Remove an earlier features.csv (and a leftover temp file) so a failure leaves none."""
    for path in (out_dir / FEATURES_FILE, out_dir / f"{FEATURES_FILE}.tmp"):
        path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Build features.csv; exit code 1 (and no output) on any problem."""
    setup_from_env()
    parser = argparse.ArgumentParser(description="Build features.csv (past and future days).")
    parser.add_argument("--clean-data", type=Path, default=DEFAULT_CLEAN_DATA)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    try:
        clear_outputs(args.out_dir)
        scope = load_scope(args.scope)
        clean = load_clean(args.clean_data)
        calendar = load_calendar(args.calendar, str(clean["state_id"].iloc[0]))
        features = build_features(clean, calendar, scope)
        path = write_features(features, args.out_dir)
    except (ScopeError, FeatureError, CleaningError, WindowError, OSError) as exc:
        clear_outputs(args.out_dir)
        logger.error("%s", exc)
        return 1
    logger.info("Wrote %s (%d rows, %d items)", path, len(features), features["item_id"].nunique())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
