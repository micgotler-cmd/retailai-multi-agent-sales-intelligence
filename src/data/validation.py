"""Data Validator logic (Agent 1, Crew 1): deterministic checks on the raw M5 files.

Each check is a small function that returns a CheckResult. run_validation()
runs them in order and builds the quality report; write_quality_report()
saves it as `quality_report.json` (interface: list of checks with status and
message, see docs/agents-and-tasks.md). The Data Validator agent calls this
through a tool (P-04); it never computes the checks itself.

Scope: structural checks (files, columns) cover the whole file; content checks
cover the configured store, and item-level checks cover the approved items
(config/data_scope.json). Missing prices before an item becomes available are
expected and reported as information (T-13 decides the cleaning policy).

Usage (from the repository root):
    uv run python -m src.data.validation
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.m5_files import (
    FILES,
    ID_COLUMNS,
    M5DataError,
    day_columns,
    day_number,
    load_calendar,
    load_store_prices,
    load_store_sales,
    missing_columns,
    read_columns,
)
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope

logger = logging.getLogger(__name__)

REPORT_SCHEMA_VERSION = "1.0.0"
PASS, WARN, FAIL, SKIPPED = "pass", "warn", "fail", "skipped"
MAX_LISTED = 20  # cap on example values listed in a check's details


@dataclass
class CheckResult:
    """Outcome of one check. A failed blocking check stops the pipeline (Gate 1, M-19)."""

    name: str
    status: str
    blocking: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class RawData:
    """The loaded raw data for one store."""

    calendar: pd.DataFrame
    sales: pd.DataFrame
    prices: pd.DataFrame


def _ok(name: str, message: str, blocking: bool = True, **details) -> CheckResult:
    return CheckResult(name, PASS, blocking, message, details)


def _bad(name: str, message: str, blocking: bool = True, **details) -> CheckResult:
    return CheckResult(name, FAIL if blocking else WARN, blocking, message, details)


def _first(values, limit: int = MAX_LISTED) -> list:
    return [v.item() if hasattr(v, "item") else v for v in list(values)[:limit]]


# --------------------------------------------------------- structural checks


def needed_files(scope: DataScope) -> dict[str, str]:
    """File keys and names the validator needs: calendar, the scope's sales file, prices."""
    sales_key = next((k for k, v in FILES.items() if v == scope.sales_file), None)
    if sales_key is None or not sales_key.startswith("sales"):
        raise ScopeError(f"Unknown sales_file {scope.sales_file!r}")
    return {k: FILES[k] for k in ("calendar", sales_key, "sell_prices")}


def check_files_present(raw_dir: Path, files: dict[str, str]) -> CheckResult:
    """All needed raw files exist."""
    missing = [name for name in files.values() if not (raw_dir / name).is_file()]
    if missing:
        return _bad(
            "files_present",
            f"Missing file(s) in {raw_dir}: {', '.join(missing)}",
            missing=missing,
        )
    return _ok("files_present", "All required files are present", files=list(files.values()))


def check_required_columns(raw_dir: Path, files: dict[str, str]) -> CheckResult:
    """Each needed file has its required columns (sales files also need d_ columns)."""
    problems = {
        name: cols
        for key, name in files.items()
        if (cols := missing_columns(key, read_columns(raw_dir / name)))
    }
    if problems:
        text = "; ".join(f"{n}: {', '.join(c)}" for n, c in problems.items())
        return _bad("required_columns", f"Missing column(s): {text}", missing=problems)
    return _ok("required_columns", "All required columns are present")


# ------------------------------------------------------------ content checks


def check_calendar(cal: pd.DataFrame) -> CheckResult:
    """No missing or duplicate dates; day ids are contiguous."""
    full = pd.date_range(cal["date"].min(), cal["date"].max(), freq="D")
    missing = sorted(set(full.date) - set(cal["date"].dt.date))
    duplicates = int(cal["date"].duplicated().sum())
    days = cal["day"].to_numpy()
    contiguous = bool(np.array_equal(days, np.arange(days.min(), days.max() + 1)))
    details = {
        "first_date": str(cal["date"].min().date()),
        "last_date": str(cal["date"].max().date()),
        "missing_dates": [str(d) for d in missing[:MAX_LISTED]],
        "duplicate_dates": duplicates,
        "day_ids_contiguous": contiguous,
    }
    if missing or duplicates or not contiguous:
        return _bad(
            "calendar_dates",
            f"Calendar has {len(missing)} missing date(s), {duplicates} duplicate date(s), "
            f"day ids contiguous: {contiguous}",
            **details,
        )
    return _ok("calendar_dates", "Calendar dates are complete and unique", **details)


def check_sales_days(sales: pd.DataFrame, cal: pd.DataFrame, scope: DataScope) -> CheckResult:
    """Day columns start at d_1, are contiguous, exist in the calendar and cover the split."""
    numbers = [day_number(d) for d in day_columns(list(sales.columns))]
    contiguous = numbers == list(range(1, len(numbers) + 1))
    not_in_calendar = sorted(set(numbers) - set(cal["day"]))
    details = {
        "first_day": numbers[0],
        "last_day": numbers[-1],
        "contiguous_from_d_1": contiguous,
        "days_not_in_calendar": _first(not_in_calendar),
        "split_last_day": scope.last_day,
    }
    problems = []
    if not contiguous:
        problems.append("day columns are not contiguous from d_1")
    if not_in_calendar:
        problems.append(f"{len(not_in_calendar)} day(s) missing from the calendar")
    if numbers[-1] < scope.last_day:
        problems.append(f"data ends at d_{numbers[-1]} but the split needs d_{scope.last_day}")
    if problems:
        return _bad("sales_days", "Sales days: " + "; ".join(problems), **details)
    return _ok("sales_days", f"Sales cover d_1 to d_{numbers[-1]}", **details)


def check_sales_ids(sales: pd.DataFrame) -> CheckResult:
    """No null id fields and no duplicate rows per item."""
    nulls = {c: int(n) for c, n in sales[ID_COLUMNS].isna().sum().items() if n}
    dup_items = sales.loc[sales["item_id"].duplicated(), "item_id"]
    dup_ids = int(sales["id"].duplicated().sum())
    details = {
        "null_id_values": nulls,
        "duplicate_item_ids": _first(dup_items),
        "duplicate_ids": dup_ids,
    }
    if nulls or len(dup_items) or dup_ids:
        return _bad(
            "sales_ids",
            f"Sales ids: {sum(nulls.values())} null value(s), {len(dup_items)} duplicate item_id(s), "
            f"{dup_ids} duplicate id(s)",
            **details,
        )
    return _ok("sales_ids", f"{len(sales)} items, ids complete and unique", **details)


def check_units(sales: pd.DataFrame) -> CheckResult:
    """units_sold is present, a whole number and nonnegative (spec s5)."""
    values = sales[day_columns(list(sales.columns))].apply(pd.to_numeric, errors="coerce")
    arr = values.to_numpy(dtype=float)
    nulls = int(np.isnan(arr).sum())
    finite = arr[~np.isnan(arr)]
    negative = int((finite < 0).sum())
    fractional = int((finite != np.floor(finite)).sum())
    details = {"null_or_non_numeric": nulls, "negative": negative, "non_integer": fractional}
    if nulls or negative or fractional:
        return _bad(
            "units_sold_valid",
            f"units_sold: {nulls} missing/non-numeric, {negative} negative, "
            f"{fractional} non-integer value(s)",
            **details,
        )
    return _ok("units_sold_valid", "All units_sold values are nonnegative whole numbers", **details)


def check_prices(prices: pd.DataFrame) -> CheckResult:
    """sell_price is positive when present; keys are complete and unique."""
    keys = ["store_id", "item_id", "wm_yr_wk"]
    null_keys = int(prices[keys].isna().any(axis=1).sum())
    duplicates = int(prices.duplicated(subset=keys).sum())
    price = pd.to_numeric(prices["sell_price"], errors="coerce")
    non_positive = int((price <= 0).sum())
    missing = int(price.isna().sum())
    details = {
        "rows": len(prices),
        "null_keys": null_keys,
        "duplicate_keys": duplicates,
        "non_positive_prices": non_positive,
        "missing_prices": missing,
    }
    if null_keys or duplicates or non_positive:
        return _bad(
            "sell_price_valid",
            f"Prices: {null_keys} null key(s), {duplicates} duplicate key(s), "
            f"{non_positive} zero or negative price(s)",
            **details,
        )
    return _ok("sell_price_valid", "Prices are positive with unique keys", **details)


def check_scope_items(sales: pd.DataFrame, scope: DataScope) -> CheckResult:
    """Every approved item exists in the store's sales."""
    missing = [i for i in scope.item_ids if i not in set(sales["item_id"])]
    if missing:
        return _bad(
            "scope_items_present",
            f"{len(missing)} approved item(s) not found in {scope.store_id}: {', '.join(missing)}",
            missing=missing,
        )
    return _ok("scope_items_present", f"All {len(scope.item_ids)} approved items are present")


def check_scope_item_prices(raw: RawData, scope: DataScope) -> CheckResult:
    """Price gaps for the approved items, split into before and after availability.

    Weeks before an item's first price are expected to be missing (not yet sold).
    A gap after the first price is reported as a warning for the null policy (T-13).
    """
    last_day = day_number(day_columns(list(raw.sales.columns))[-1])
    weeks = np.sort(raw.calendar.loc[raw.calendar["day"] <= last_day, "wm_yr_wk"].unique())
    priced = raw.prices.dropna(subset=["sell_price"])
    per_item = {}
    for item in scope.item_ids:
        item_weeks = set(priced.loc[priced["item_id"] == item, "wm_yr_wk"])
        if not item_weeks:
            per_item[item] = {
                "weeks_before_first_price": len(weeks),
                "gaps_after_first_price": None,
            }
            continue
        first = min(item_weeks)
        after = [w for w in weeks if w >= first]
        per_item[item] = {
            "weeks_before_first_price": int((weeks < first).sum()),
            "gaps_after_first_price": sum(1 for w in after if w not in item_weeks),
        }
    no_price = [i for i, v in per_item.items() if v["gaps_after_first_price"] is None]
    gaps = {
        i: v["gaps_after_first_price"] for i, v in per_item.items() if v["gaps_after_first_price"]
    }
    details = {"per_item": per_item}
    if no_price or gaps:
        return _bad(
            "scope_item_prices",
            f"{len(no_price)} approved item(s) without any price, {len(gaps)} with price gaps "
            "after their first price (see T-13)",
            blocking=False,
            **details,
        )
    before = sum(v["weeks_before_first_price"] for v in per_item.values())
    return _ok(
        "scope_item_prices",
        "Approved items have a price in every week after their first price; "
        f"{before} item-week(s) before availability have no price (expected)",
        blocking=False,
        **details,
    )


def check_store_zero_days(sales: pd.DataFrame, cal: pd.DataFrame) -> CheckResult:
    """Days on which the whole store sold nothing (for example a closure)."""
    days = day_columns(list(sales.columns))
    totals = sales[days].apply(pd.to_numeric, errors="coerce").sum(axis=0)
    zero_days = [day_number(d) for d in totals[totals == 0].index]
    date_of = dict(zip(cal["day"], cal["date"].dt.date.astype(str)))
    dates = [date_of.get(d, f"d_{d}") for d in zero_days]
    if dates:
        return _bad(
            "store_zero_sales_days",
            f"{len(dates)} day(s) with zero sales for the whole store: {', '.join(dates[:5])}"
            + (" ..." if len(dates) > 5 else ""),
            blocking=False,
            dates=dates,
        )
    return _ok("store_zero_sales_days", "No store-wide zero-sales days", blocking=False)


# ------------------------------------------------------------------- runner

CONTENT_CHECKS: list[tuple[str, Callable[[RawData, DataScope], CheckResult]]] = [
    ("calendar_dates", lambda r, s: check_calendar(r.calendar)),
    ("sales_days", lambda r, s: check_sales_days(r.sales, r.calendar, s)),
    ("sales_ids", lambda r, s: check_sales_ids(r.sales)),
    ("units_sold_valid", lambda r, s: check_units(r.sales)),
    ("sell_price_valid", lambda r, s: check_prices(r.prices)),
    ("scope_items_present", lambda r, s: check_scope_items(r.sales, s)),
    ("scope_item_prices", check_scope_item_prices),
    ("store_zero_sales_days", lambda r, s: check_store_zero_days(r.sales, r.calendar)),
]


def load_raw(raw_dir: Path, scope: DataScope) -> RawData:
    """Load the calendar, the store's sales (raw types) and the store's prices."""
    return RawData(
        calendar=load_calendar(raw_dir / FILES["calendar"]),
        sales=load_store_sales(raw_dir / scope.sales_file, scope.store_id, int_days=False),
        prices=load_store_prices(raw_dir / FILES["sell_prices"], scope.store_id),
    )


def run_checks(raw_dir: Path, scope: DataScope) -> list[CheckResult]:
    """Run all checks in order; later checks are skipped when the files cannot be read."""
    files = needed_files(scope)
    results = [check_files_present(raw_dir, files)]
    if results[-1].status == PASS:
        results.append(check_required_columns(raw_dir, files))
    if results[-1].status != PASS:
        return results + _skipped(results, "required files or columns are missing")

    try:
        raw = load_raw(raw_dir, scope)
    except M5DataError as exc:
        results.append(_bad("store_present", str(exc)))
        return results + _skipped(results, "the store's data could not be loaded")
    results.append(_ok("store_present", f"Store {scope.store_id} found ({len(raw.sales)} items)"))

    for name, check in CONTENT_CHECKS:
        try:
            results.append(check(raw, scope))
        except Exception as exc:  # a crashing check must be reported, never hidden
            logger.exception("Check %s raised an error", name)
            results.append(_bad(name, f"Check could not run: {type(exc).__name__}: {exc}"))
    return results


def _skipped(done: list[CheckResult], reason: str) -> list[CheckResult]:
    """Results for every check that has not run yet, marked as skipped."""
    names = ["files_present", "required_columns", "store_present"]
    names += [name for name, _ in CONTENT_CHECKS]
    ran = {r.name for r in done}
    return [CheckResult(n, SKIPPED, True, f"Not run: {reason}") for n in names if n not in ran]


def build_report(results: list[CheckResult], scope: DataScope) -> dict:
    """Assemble quality_report.json content; status is 'fail' if any blocking check failed."""
    counts = {s: sum(r.status == s for r in results) for s in (PASS, WARN, FAIL, SKIPPED)}
    blocking_failures = [r.name for r in results if r.blocking and r.status == FAIL]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "store_id": scope.store_id,
        "sales_file": scope.sales_file,
        "items_in_scope": len(scope.item_ids),
        "status": FAIL if blocking_failures else PASS,
        "summary": {
            "checks": len(results),
            "passed": counts[PASS],
            "warnings": counts[WARN],
            "failed": counts[FAIL],
            "skipped": counts[SKIPPED],
            "blocking_failures": blocking_failures,
        },
        "checks": [asdict(r) for r in results],
    }


def run_validation(raw_dir: Path, scope: DataScope) -> dict:
    """Run every check and return the quality report; each result is logged."""
    results = run_checks(raw_dir, scope)
    for r in results:
        log = logger.warning if r.status in (WARN, FAIL) else logger.info
        log("Check %s: %s (%s)", r.name, r.status, r.message)
    report = build_report(results, scope)
    logger.info("Validation status: %s", report["status"])
    return report


def write_quality_report(report: dict, path: Path) -> Path:
    """Save the report as JSON (contains counts and messages only, no raw rows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Validate the raw files; exit code 0 when no blocking check failed, else 1."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Validate the raw M5 files (Agent 1 logic).")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument(
        "--out", type=Path, default=Path("artifacts/validation/quality_report.json")
    )
    args = parser.parse_args(argv)
    try:
        scope = load_scope(args.scope)
        report = run_validation(args.raw_dir, scope)
    except ScopeError as exc:
        logger.error("%s", exc)
        return 1
    logger.info("Wrote %s", write_quality_report(report, args.out))
    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
