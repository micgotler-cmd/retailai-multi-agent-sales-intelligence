"""Cleaning of the long table into `clean_data.csv` (Agent 2, Data Cleaner logic, P-03).

Rules (T-13, approved 2026-11-23):
1. Rows before an item's first sale are dropped: the item was not stocked yet,
   so those zeros are not demand. The first sale is found on the training
   period only (T-09), so no validation or test data is used.
2. Store closures: 25 December gets `store_closed = 1` (units stay 0). The
   rule is a known calendar date, so the flag is safe as a forecast feature.
3. Missing prices are never imputed. A missing or non-positive price on a
   kept row fails the cleaning with a readable error.

Every action is counted in the cleaning log. The Data Cleaner agent calls this
through a tool (P-04); it never edits data itself.

Usage (from the repository root): validation, ETL and cleaning in one run:
    uv run python -m src.data.cleaning
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.data.etl import KEYS, OUTPUT_COLUMNS, build_long_table, write_long_table
from src.data.m5_files import M5DataError
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope
from src.data.validation import PASS, run_validation, write_quality_report

logger = logging.getLogger(__name__)

LOG_SCHEMA_VERSION = "1.0.0"
CLEAN_COLUMNS = OUTPUT_COLUMNS + ["store_closed"]
CLOSURE_MONTH_DAY = (12, 25)  # store closed on Christmas Day (validation finding)


class CleaningError(Exception):
    """Raised when the data cannot be cleaned under the approved rules."""


def day_to_date(long: pd.DataFrame, scope: DataScope) -> pd.Timestamp:
    """Date of d_1, checking the long table covers days 1..scope.last_day without gaps."""
    dates = pd.DatetimeIndex(long["date"].drop_duplicates()).sort_values()
    if len(dates) != scope.last_day or (dates[-1] - dates[0]).days != scope.last_day - 1:
        raise CleaningError(
            f"Long table must cover days 1..{scope.last_day} without gaps; found {len(dates)} dates"
        )
    return dates[0]


def date_of_day(day_1: pd.Timestamp, day: int) -> pd.Timestamp:
    """Date of M5 day number `day`."""
    return day_1 + pd.Timedelta(days=day - 1)


def first_sale_dates(long: pd.DataFrame, train_last_date: pd.Timestamp) -> pd.Series:
    """First date with units_sold > 0 per item, looking at the training period only."""
    train = long[(long["date"] <= train_last_date) & (long["units_sold"] > 0)]
    first = train.groupby("item_id")["date"].min()
    never = sorted(set(long["item_id"]) - set(first.index))
    if never:
        raise CleaningError(f"Item(s) with no sale in the training period: {', '.join(never)}")
    return first


def drop_pre_launch(long: pd.DataFrame, first_sale: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Drop each item's rows before its first sale; return the rows dropped per item."""
    keep = long["date"] >= long["item_id"].map(first_sale)
    dropped = long.loc[~keep].groupby("item_id").size()
    counts = {item: int(dropped.get(item, 0)) for item in first_sale.index}
    return long.loc[keep].copy(), counts


def add_store_closed(df: pd.DataFrame) -> pd.DataFrame:
    """Add store_closed = 1 on 25 December, else 0."""
    month, day = CLOSURE_MONTH_DAY
    df["store_closed"] = ((df["date"].dt.month == month) & (df["date"].dt.day == day)).astype(
        "int64"
    )
    return df


def check_prices(df: pd.DataFrame) -> None:
    """Fail on any missing or non-positive price in the kept rows (no imputation)."""
    missing = df[df["sell_price"].isna()]
    if len(missing):
        sample = missing[["item_id", "date"]].head(5).astype(str).values.tolist()
        raise CleaningError(
            f"{len(missing)} kept row(s) have no sell_price, for example {sample}. "
            "Prices are never imputed (T-13); check the raw data."
        )
    if (df["sell_price"] <= 0).any():
        raise CleaningError("Kept rows contain zero or negative sell_price")


def check_clean(df: pd.DataFrame, last_date: pd.Timestamp) -> None:
    """Final checks: unique keys, no gaps per item up to last_date, units >= 0, sorted."""
    if df.duplicated(subset=KEYS).any():
        raise CleaningError("Clean data has duplicate (store_id, item_id, date) rows")
    if (df["units_sold"] < 0).any():
        raise CleaningError("Clean data has negative units_sold")
    for item, dates in df.groupby("item_id")["date"]:
        expected = (dates.max() - dates.min()).days + 1
        if dates.max() != last_date or len(dates) != expected:
            raise CleaningError(f"Item {item}: dates are not continuous up to {last_date.date()}")
    order = df[["item_id", "date"]].reset_index(drop=True)
    if not order.equals(order.sort_values(["item_id", "date"]).reset_index(drop=True)):
        raise CleaningError("Clean data is not sorted by item_id, date")


def clean(long: pd.DataFrame, scope: DataScope) -> tuple[pd.DataFrame, dict]:
    """Apply the T-13 rules to the ETL output; return clean data and the cleaning log."""
    day_1 = day_to_date(long, scope)
    train_last = date_of_day(day_1, scope.split["train"].last_day)
    last_date = date_of_day(day_1, scope.last_day)

    first_sale = first_sale_dates(long, train_last)
    df, dropped = drop_pre_launch(long, first_sale)
    df = add_store_closed(df)
    check_prices(df)
    df = df[CLEAN_COLUMNS].sort_values(["item_id", "date"], kind="stable").reset_index(drop=True)
    check_clean(df, last_date)

    closed = df[df["store_closed"] == 1]
    log = {
        "schema_version": LOG_SCHEMA_VERSION,
        "store_id": scope.store_id,
        "items": len(first_sale),
        "rows_in": len(long),
        "rows_out": len(df),
        "first_date": str(df["date"].min().date()),
        "last_date": str(last_date.date()),
        "actions": [
            {
                "action": "drop_rows_before_first_sale",
                "rule": "T-13 rule 1; first sale found on the training period only (T-09)",
                "rows_dropped": sum(dropped.values()),
                "rows_dropped_per_item": dropped,
                "first_sale_date_per_item": {k: str(v.date()) for k, v in first_sale.items()},
            },
            {
                "action": "flag_store_closed",
                "rule": "T-13 rule 2; store_closed = 1 on 25 December, units unchanged",
                "dates": sorted(str(d.date()) for d in closed["date"].unique()),
                "rows_flagged": len(closed),
                "flagged_rows_with_sales": int((closed["units_sold"] > 0).sum()),
            },
            {
                "action": "check_prices",
                "rule": "T-13 rule 3; no imputation, missing or non-positive price fails",
                "missing_prices": 0,
                "rows_checked": len(df),
            },
        ],
    }
    logger.info(
        "Cleaned: %d -> %d rows; %d pre-launch rows dropped; %d closure rows flagged",
        len(long),
        len(df),
        sum(dropped.values()),
        len(closed),
    )
    return df, log


def write_outputs(df: pd.DataFrame, log: dict, out_dir: Path) -> list[Path]:
    """Write clean_data.csv and cleaning_log.json. Git-ignored folders only (T-04)."""
    data_path = write_long_table(df, out_dir / "clean_data.csv")
    log_path = out_dir / "cleaning_log.json"
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return [data_path, log_path]


def main(argv: list[str] | None = None) -> int:
    """Validate the raw files, run the ETL and clean; exit code 1 on any blocking problem."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Validate, reshape and clean the M5 data.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/clean"))
    args = parser.parse_args(argv)
    try:
        scope = load_scope(args.scope)
        report = run_validation(args.raw_dir, scope)
        write_quality_report(report, args.out_dir / "quality_report.json")
        if report["status"] != PASS:
            logger.error("Validation failed: %s", report["summary"]["blocking_failures"])
            return 1
        df, log = clean(build_long_table(args.raw_dir, scope), scope)
    except (ScopeError, M5DataError, CleaningError) as exc:
        logger.error("%s", exc)
        return 1
    for path in write_outputs(df, log, args.out_dir):
        logger.info("Wrote %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
