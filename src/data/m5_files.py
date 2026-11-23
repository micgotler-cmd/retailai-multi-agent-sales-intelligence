"""Shared names and readers for the raw Kaggle M5 files.

Used by the inspection script and the Data Validator logic, so file names,
required columns and loaders are defined once.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

FILES = {
    "calendar": "calendar.csv",
    "sales_validation": "sales_train_validation.csv",
    "sales_evaluation": "sales_train_evaluation.csv",
    "sell_prices": "sell_prices.csv",
}

ID_COLUMNS = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]

REQUIRED_COLUMNS = {
    "calendar": ["date", "wm_yr_wk", "d"],
    "sales_validation": ID_COLUMNS,
    "sales_evaluation": ID_COLUMNS,
    "sell_prices": ["store_id", "item_id", "wm_yr_wk", "sell_price"],
}

DAY_PATTERN = re.compile(r"^d_(\d+)$")


class M5DataError(Exception):
    """Raised when the raw M5 files are missing or do not have the expected shape."""


def file_paths(raw_dir: Path) -> dict[str, Path]:
    """Expected path of each raw file (existence is not checked)."""
    return {key: raw_dir / name for key, name in FILES.items()}


def missing_files(raw_dir: Path) -> list[str]:
    """Names of the expected raw files that do not exist in raw_dir."""
    return [p.name for p in file_paths(raw_dir).values() if not p.is_file()]


def check_files(raw_dir: Path) -> dict[str, Path]:
    """Return the path of each required file, or raise if any is missing."""
    missing = missing_files(raw_dir)
    if missing:
        raise M5DataError(
            "Missing M5 file(s): "
            + ", ".join(missing)
            + f" in {raw_dir}. Download them from Kaggle into data/raw/ (see README, Data source)."
        )
    return file_paths(raw_dir)


def read_columns(path: Path) -> list[str]:
    """Read only the header row of a CSV file."""
    return list(pd.read_csv(path, nrows=0).columns)


def missing_columns(name: str, columns: list[str]) -> list[str]:
    """Required columns of file `name` that are absent (sales files also need d_ columns)."""
    missing = [c for c in REQUIRED_COLUMNS[name] if c not in columns]
    if name.startswith("sales") and not day_columns(columns):
        missing.append("d_1, d_2, ... (day columns)")
    return missing


def check_columns(name: str, columns: list[str]) -> None:
    """Raise if a file lacks a required column."""
    missing = missing_columns(name, columns)
    if missing:
        raise M5DataError(f"{FILES[name]} is missing column(s): {', '.join(missing)}")


def day_columns(columns: list[str]) -> list[str]:
    """Return the d_<n> columns sorted by day number."""
    days = [c for c in columns if DAY_PATTERN.match(c)]
    return sorted(days, key=day_number)


def day_number(column: str) -> int:
    """Convert 'd_123' to 123."""
    match = DAY_PATTERN.match(column)
    if match is None:
        raise M5DataError(f"Not a day column: {column}")
    return int(match.group(1))


def load_calendar(path: Path) -> pd.DataFrame:
    """Load the calendar with parsed dates and a numeric day index, sorted by day."""
    cal = pd.read_csv(path, usecols=REQUIRED_COLUMNS["calendar"], parse_dates=["date"])
    cal["day"] = cal["d"].map(day_number)
    return cal.sort_values("day").reset_index(drop=True)


def load_store_sales(
    path: Path, store_id: str, chunksize: int = 5000, int_days: bool = True
) -> pd.DataFrame:
    """Load the wide sales rows of one store, reading the file in chunks.

    With int_days=False the day columns keep the type pandas infers, so the
    validator can detect missing or non-integer values. Raises if the store is
    absent. Duplicate rows are not removed here; the validator reports them.
    """
    dtypes = {c: "int32" for c in day_columns(read_columns(path))} if int_days else None
    parts = [
        chunk[chunk["store_id"] == store_id]
        for chunk in pd.read_csv(path, dtype=dtypes, chunksize=chunksize)
    ]
    sales = pd.concat(parts, ignore_index=True)
    if sales.empty:
        raise M5DataError(f"Store {store_id!r} not found in {path.name}")
    return sales.sort_values("item_id", kind="stable").reset_index(drop=True)


def load_store_prices(path: Path, store_id: str) -> pd.DataFrame:
    """Load the weekly prices of one store."""
    prices = pd.read_csv(path, usecols=REQUIRED_COLUMNS["sell_prices"])
    return prices[prices["store_id"] == store_id].reset_index(drop=True)
