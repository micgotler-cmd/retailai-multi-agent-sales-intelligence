"""Wide-to-long ETL for the approved items (Agent 2, Data Cleaner logic, P-02).

Reads the store's wide sales rows, keeps the approved items (config/data_scope.json),
melts them to one row per item per day, joins the calendar on `d` and the weekly
prices on (store_id, item_id, wm_yr_wk). The result has the normalized columns of
spec s5, sorted by item_id and date.

No cleaning happens here: missing prices stay null, and store closures and the
days before an item's first sale are kept as they are. Those are cleaning
decisions (P-03, T-13). The output holds row-level M5 data, so it is written
only to git-ignored folders and never committed (T-04).

Usage (from the repository root):
    uv run python -m src.data.etl
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from src.data.m5_files import (
    FILES,
    ID_COLUMNS,
    M5DataError,
    day_columns,
    day_number,
    load_store_prices,
    load_store_sales,
    read_columns,
)
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "date",
    "store_id",
    "item_id",
    "dept_id",
    "cat_id",
    "state_id",
    "units_sold",
    "sell_price",
    "wm_yr_wk",
    "event_name_1",
    "event_type_1",
    "snap",
]
CALENDAR_COLUMNS = ["date", "wm_yr_wk", "d", "event_name_1", "event_type_1"]
KEYS = ["store_id", "item_id", "date"]


def load_scope_sales(raw_dir: Path, scope: DataScope) -> pd.DataFrame:
    """Wide sales rows of the approved items, limited to days 1..scope.last_day."""
    sales = load_store_sales(raw_dir / scope.sales_file, scope.store_id)
    missing = [i for i in scope.item_ids if i not in set(sales["item_id"])]
    if missing:
        raise M5DataError(f"Approved item(s) not in {scope.store_id}: {', '.join(missing)}")
    sales = sales[sales["item_id"].isin(scope.item_ids)]
    if sales["item_id"].duplicated().any():
        raise M5DataError("Duplicate sales rows for an approved item")

    days = day_columns(list(sales.columns))
    if day_number(days[-1]) < scope.last_day:
        raise M5DataError(f"Sales end at {days[-1]}; the split needs d_{scope.last_day}")
    keep = [d for d in days if day_number(d) <= scope.last_day]
    return sales[ID_COLUMNS + keep].reset_index(drop=True)


def store_state(sales: pd.DataFrame) -> str:
    """The single state_id of the store's rows (selects the SNAP column)."""
    states = sales["state_id"].dropna().unique()
    if len(states) != 1:
        raise M5DataError(f"Expected one state for the store, found {sorted(states)}")
    return str(states[0])


def load_calendar_for_state(path: Path, state: str) -> pd.DataFrame:
    """Calendar with events and the SNAP flag of `state`, renamed to `snap`."""
    snap = f"snap_{state}"
    missing = [c for c in CALENDAR_COLUMNS + [snap] if c not in read_columns(path)]
    if missing:
        raise M5DataError(f"{path.name} is missing column(s): {', '.join(missing)}")
    cal = pd.read_csv(path, usecols=CALENDAR_COLUMNS + [snap], parse_dates=["date"])
    return cal.rename(columns={snap: "snap"})


def melt_sales(sales: pd.DataFrame) -> pd.DataFrame:
    """One row per item per day: id columns, d, units_sold."""
    return sales.melt(
        id_vars=ID_COLUMNS,
        value_vars=day_columns(list(sales.columns)),
        var_name="d",
        value_name="units_sold",
    )


def join_calendar(long: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Add date, week, events and SNAP; every day must exist in the calendar."""
    if cal["d"].duplicated().any():
        raise M5DataError("Calendar has duplicate d values")
    joined = long.merge(cal, on="d", how="left")
    unmatched = joined["date"].isna()
    if unmatched.any():
        sample = ", ".join(joined.loc[unmatched, "d"].unique()[:5])
        raise M5DataError(f"{int(unmatched.sum())} row(s) have no calendar day: {sample}")
    return joined


def join_prices(long: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Left join the weekly price; weeks without a price keep sell_price null."""
    keys = ["store_id", "item_id", "wm_yr_wk"]
    if prices.duplicated(subset=keys).any():
        raise M5DataError("sell_prices has duplicate (store_id, item_id, wm_yr_wk) keys")
    return long.merge(prices[keys + ["sell_price"]], on=keys, how="left")


def check_input_files(raw_dir: Path, scope: DataScope) -> None:
    """Raise a readable error if a file the ETL reads is missing."""
    needed = [scope.sales_file, FILES["calendar"], FILES["sell_prices"]]
    missing = [name for name in needed if not (raw_dir / name).is_file()]
    if missing:
        raise M5DataError(f"Missing file(s) in {raw_dir}: {', '.join(missing)}")


def build_long_table(raw_dir: Path, scope: DataScope) -> pd.DataFrame:
    """Run the ETL and return the long table with OUTPUT_COLUMNS."""
    check_input_files(raw_dir, scope)
    sales = load_scope_sales(raw_dir, scope)
    cal = load_calendar_for_state(raw_dir / FILES["calendar"], store_state(sales))
    prices = load_store_prices(raw_dir / FILES["sell_prices"], scope.store_id)

    long = join_prices(join_calendar(melt_sales(sales), cal), prices)
    long["units_sold"] = long["units_sold"].astype("int64")
    long["snap"] = long["snap"].astype("int64")
    long = long[OUTPUT_COLUMNS].sort_values(["item_id", "date"], kind="stable")
    long = long.reset_index(drop=True)

    if long.duplicated(subset=KEYS).any():
        raise M5DataError("Long table has duplicate (store_id, item_id, date) rows")
    logger.info(
        "Long table: %d rows (%d items x %d days), %d missing prices",
        len(long),
        long["item_id"].nunique(),
        long["date"].nunique(),
        int(long["sell_price"].isna().sum()),
    )
    return long


def write_long_table(long: pd.DataFrame, path: Path) -> Path:
    """Write the table as CSV with ISO dates. Use git-ignored folders only (T-04)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    long.to_csv(path, index=False, date_format="%Y-%m-%d")
    return path


def main(argv: list[str] | None = None) -> int:
    """Build the long table for the approved scope; exit code 1 on a data or scope error."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Wide-to-long ETL for the approved items.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--out", type=Path, default=Path("artifacts/etl/long_data.csv"))
    args = parser.parse_args(argv)
    try:
        long = build_long_table(args.raw_dir, load_scope(args.scope))
    except (M5DataError, ScopeError) as exc:
        logger.error("%s", exc)
        return 1
    logger.info("Wrote %s", write_long_table(long, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
