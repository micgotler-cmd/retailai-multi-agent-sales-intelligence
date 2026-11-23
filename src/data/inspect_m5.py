"""Read-only inspection of the raw Kaggle M5 files (first data task, P-02).

Checks that the expected files and columns exist, summarizes the calendar and
the sales of one store, computes per-item statistics on the training period
only, and applies the approved split (T-09) and item selection (T-03).

The output contains aggregates only (T-04 condition 6): no raw sales rows are
copied. Nothing here modifies the raw files. Thresholds are the approved T-03
values (2026-11-23).

Usage (from the repository root):
    uv run python -m src.data.inspect_m5 --store-id CA_1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.m5_files import (
    FILES,
    M5DataError,
    check_columns,
    check_files,
    day_columns,
    day_number,
    load_calendar,
    load_store_prices,
    load_store_sales,
    read_columns,
)

logger = logging.getLogger(__name__)

HORIZON_DAYS = 28  # Forecast horizon, spec s8 (D-03).

TIERS = ("high", "medium", "low")

# Kept as the inspection's error name; raised by the shared readers too.
InspectionError = M5DataError


@dataclass(frozen=True)
class SelectionParams:
    """Item-selection thresholds (T-03, approved 2026-11-23)."""

    n_items: int = 20
    min_history_days: int = 365
    max_zero_share: float = 0.8
    min_price_coverage: float = 0.95


# ---------------------------------------------------------------- summaries


def calendar_summary(cal: pd.DataFrame) -> dict:
    """Date range, gaps in the date sequence and whether day ids are contiguous."""
    full = pd.date_range(cal["date"].min(), cal["date"].max(), freq="D")
    missing = sorted(set(full.date) - set(cal["date"].dt.date))
    days = cal["day"].to_numpy()
    return {
        "rows": len(cal),
        "first_date": str(cal["date"].min().date()),
        "last_date": str(cal["date"].max().date()),
        "first_day": int(days.min()),
        "last_day": int(days.max()),
        "missing_dates": [str(d) for d in missing],
        "day_ids_contiguous": bool(np.array_equal(days, np.arange(days.min(), days.max() + 1))),
        "duplicate_dates": int(cal["date"].duplicated().sum()),
    }


def sales_summary(sales: pd.DataFrame, cal: pd.DataFrame) -> dict:
    """Shape, day range and hierarchy counts for one store's sales."""
    days = day_columns(list(sales.columns))
    first, last = day_number(days[0]), day_number(days[-1])
    known_days = set(cal["day"])
    return {
        "items": len(sales),
        "departments": sorted(sales["dept_id"].unique().tolist()),
        "categories": sorted(sales["cat_id"].unique().tolist()),
        "first_day": first,
        "last_day": last,
        "n_days": len(days),
        "days_missing_from_calendar": [d for d in days if day_number(d) not in known_days],
        "day_columns_contiguous": [day_number(d) for d in days] == list(range(first, last + 1)),
        "negative_values": int((sales[days].to_numpy() < 0).sum()),
    }


def compare_sales_files(validation: pd.DataFrame, evaluation: pd.DataFrame) -> dict:
    """Check whether the validation file is an exact prefix of the evaluation file."""
    val_days = day_columns(list(validation.columns))
    eval_days = day_columns(list(evaluation.columns))
    shared = [d for d in val_days if d in set(eval_days)]
    same_items = validation["item_id"].tolist() == evaluation["item_id"].tolist()
    identical = (
        same_items
        and len(shared) == len(val_days)
        and bool(np.array_equal(validation[shared].to_numpy(), evaluation[shared].to_numpy()))
    )
    return {
        "validation_days": len(val_days),
        "evaluation_days": len(eval_days),
        "same_items": same_items,
        "validation_is_prefix_of_evaluation": identical,
    }


def propose_split(last_day: int, cal: pd.DataFrame, horizon: int = HORIZON_DAYS) -> dict:
    """Chronological split (T-09): train, validation, test (horizon days each)."""
    if last_day <= 3 * horizon:
        raise InspectionError(f"Only {last_day} days of history; need more than {3 * horizon}")
    date_of = dict(zip(cal["day"], cal["date"].dt.date.astype(str)))
    bounds = {
        "train": (1, last_day - 2 * horizon),
        "validation": (last_day - 2 * horizon + 1, last_day - horizon),
        "test": (last_day - horizon + 1, last_day),
    }
    return {
        name: {
            "first_day": a,
            "last_day": b,
            "first_date": date_of.get(a),
            "last_date": date_of.get(b),
        }
        for name, (a, b) in bounds.items()
    }


def price_missing_summary(stats: pd.DataFrame) -> dict:
    """Store-level view of missing prices in the training period (input for T-13)."""
    sold = stats.dropna(subset=["first_sale_day"])
    first_price = sold["first_price_day"]
    return {
        "items_with_full_price_coverage": int((sold["price_coverage"] >= 1.0).sum()),
        "items_below_95pct_coverage": int((sold["price_coverage"] < 0.95).sum()),
        "mean_price_coverage": round(float(sold["price_coverage"].mean()), 4),
        "items_without_any_training_price": int(first_price.isna().sum()),
        "items_priced_after_first_sale_week": int(
            (sold["first_price_week"] > sold["first_sale_week"]).sum()
        ),
    }


# ------------------------------------------------------------- item statistics


def compute_item_stats(
    sales: pd.DataFrame, cal: pd.DataFrame, prices: pd.DataFrame, train_last_day: int
) -> pd.DataFrame:
    """Per-item statistics on days 1..train_last_day only (no validation/test data).

    History, mean units and zero share are measured from each item's first
    observed sale through train_last_day, because M5 items show zeros before
    they were stocked; those leading zeros are not counted. Price coverage is
    the share of training weeks from the first-sale week onward that have a
    sell_price. first_price_week and first_sale_week show whether prices
    start before, with or after the first sale.
    """
    days = [d for d in day_columns(list(sales.columns)) if day_number(d) <= train_last_day]
    units = sales[days].to_numpy(dtype=float)
    n_days = units.shape[1]

    sold = units > 0
    has_sale = sold.any(axis=1)
    first_idx = np.where(has_sale, sold.argmax(axis=1), n_days)
    active = np.arange(n_days)[None, :] >= first_idx[:, None]
    active_days = active.sum(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        mean_units = np.where(active, units, 0).sum(axis=1) / active_days
        zero_share = (active & ~sold).sum(axis=1) / active_days

    stats = sales[["item_id", "dept_id", "cat_id"]].copy()
    stats["first_sale_day"] = np.where(has_sale, first_idx + 1, np.nan)
    stats["history_days"] = active_days
    stats["mean_units"] = np.where(has_sale, mean_units, np.nan)
    stats["zero_share"] = np.where(has_sale, zero_share, np.nan)
    stats["price_coverage"] = _price_coverage(sales, cal, prices, first_idx + 1, train_last_day)

    week_of_day = dict(zip(cal["day"], cal["wm_yr_wk"]))
    stats["first_sale_week"] = [
        week_of_day.get(int(d)) if not np.isnan(d) else np.nan for d in stats["first_sale_day"]
    ]
    train_weeks = set(cal.loc[cal["day"] <= train_last_day, "wm_yr_wk"])
    priced = prices.dropna(subset=["sell_price"])
    first_week = priced[priced["wm_yr_wk"].isin(train_weeks)].groupby("item_id")["wm_yr_wk"].min()
    stats["first_price_week"] = stats["item_id"].map(first_week)
    first_day_of_week = cal.groupby("wm_yr_wk")["day"].min()
    stats["first_price_day"] = stats["first_price_week"].map(first_day_of_week)
    return stats


def _price_coverage(
    sales: pd.DataFrame,
    cal: pd.DataFrame,
    prices: pd.DataFrame,
    first_day: np.ndarray,
    train_last_day: int,
) -> np.ndarray:
    """Share of training weeks (from the first-sale week) that have a price."""
    train_cal = cal[cal["day"] <= train_last_day]
    weeks = np.sort(train_cal["wm_yr_wk"].unique())
    week_of_day = dict(zip(train_cal["day"], train_cal["wm_yr_wk"]))

    priced = prices.dropna(subset=["sell_price"])
    priced = priced[priced["wm_yr_wk"].isin(weeks)]
    has_price = (
        pd.crosstab(priced["item_id"], priced["wm_yr_wk"])
        .reindex(index=sales["item_id"], columns=weeks, fill_value=0)
        .to_numpy()
        > 0
    )
    coverage = np.full(len(sales), np.nan)
    for i, day in enumerate(first_day):
        if day > train_last_day:
            continue
        in_scope = weeks >= week_of_day[int(day)]
        coverage[i] = has_price[i, in_scope].mean()
    return coverage


# ------------------------------------------------------------- item selection


def tier_counts(n_items: int) -> dict[str, int]:
    """Split n items over high/medium/low as evenly as possible (20 -> 7/7/6)."""
    base, extra = divmod(n_items, len(TIERS))
    return {tier: base + (1 if i < extra else 0) for i, tier in enumerate(TIERS)}


def spread_positions(pool_size: int, n: int) -> np.ndarray:
    """Positions of n picks spread evenly over a sorted pool of pool_size items.

    The pool is cut into n equal slices and the middle element of each slice is
    taken, so the picks cover the whole range without using randomness.
    """
    if n > pool_size:
        raise InspectionError(f"Cannot pick {n} items from a pool of {pool_size}")
    return np.floor((np.arange(n) + 0.5) * pool_size / n).astype(int)


def select_items(stats: pd.DataFrame, params: SelectionParams) -> tuple[pd.DataFrame, dict]:
    """Select items by the T-03 method: eligibility, demand tiers, deterministic spread.

    Eligible items are ranked by mean daily units (ties broken by item_id) and
    split into three equal-size tiers. Within each tier the picks are spread
    evenly over the demand range (see spread_positions). No random seed is used.
    """
    eligible = stats[
        (stats["history_days"] >= params.min_history_days)
        & (stats["zero_share"] <= params.max_zero_share)
        & (stats["price_coverage"] >= params.min_price_coverage)
    ].copy()
    counts = tier_counts(params.n_items)
    if len(eligible) < max(params.n_items, len(TIERS)):
        raise InspectionError(
            f"Only {len(eligible)} eligible items for {params.n_items} requested; relax thresholds"
        )

    eligible = eligible.sort_values(["mean_units", "item_id"], ascending=[False, True])
    ranks = np.arange(1, len(eligible) + 1)
    eligible["tier"] = pd.qcut(ranks, len(TIERS), labels=list(TIERS)).astype(str)

    picks = []
    for tier in TIERS:
        pool = eligible[eligible["tier"] == tier].sort_values(
            ["mean_units", "item_id"], ascending=[False, True]
        )
        if len(pool) < counts[tier]:
            raise InspectionError(f"Tier {tier!r} has {len(pool)} items, needs {counts[tier]}")
        picks.append(pool.iloc[spread_positions(len(pool), counts[tier])])
    selected = pd.concat(picks, ignore_index=True)

    tier_bounds = eligible.groupby("tier")["mean_units"].agg(["min", "max", "count"])
    info = {
        "params": asdict(params),
        "method": "deterministic stratified spread within demand tiers; no random seed",
        "items_in_store": len(stats),
        "eligible_items": len(eligible),
        "excluded": {
            "short_history": int((stats["history_days"] < params.min_history_days).sum()),
            "too_sparse": int((stats["zero_share"] > params.max_zero_share).sum()),
            "low_price_coverage": int((stats["price_coverage"] < params.min_price_coverage).sum()),
        },
        "tier_counts": counts,
        "tier_mean_units": {
            t: {k: round(float(v), 3) for k, v in tier_bounds.loc[t].items()} for t in TIERS
        },
        "selected_item_ids": selected["item_id"].tolist(),
    }
    return selected, info


# --------------------------------------------------------------------- report


def inspect(raw_dir: Path, store_id: str, params: SelectionParams) -> tuple[dict, pd.DataFrame]:
    """Run the full read-only inspection and return the report and per-item stats."""
    paths = check_files(raw_dir)
    for name, path in paths.items():
        check_columns(name, read_columns(path))
    logger.info("All required files and columns present in %s", raw_dir)

    cal = load_calendar(paths["calendar"])
    evaluation = load_store_sales(paths["sales_evaluation"], store_id)
    validation = load_store_sales(paths["sales_validation"], store_id)
    if evaluation["item_id"].duplicated().any():
        raise InspectionError(f"Duplicate item_id rows for store {store_id}")
    prices = load_store_prices(paths["sell_prices"], store_id)
    logger.info("Loaded %d items for store %s", len(evaluation), store_id)

    sales_info = sales_summary(evaluation, cal)
    split = propose_split(sales_info["last_day"], cal)
    stats = compute_item_stats(evaluation, cal, prices, split["train"]["last_day"])
    selected, selection = select_items(stats, params)

    report = {
        "store_id": store_id,
        "sales_file_used": FILES["sales_evaluation"],
        "calendar": calendar_summary(cal),
        "sales": sales_info,
        "sales_files_comparison": compare_sales_files(validation, evaluation),
        "split": split,
        "training_period": {
            "zero_share_median": round(float(stats["zero_share"].median()), 4),
            "mean_units_median": round(float(stats["mean_units"].median()), 4),
            "items_never_sold": int(stats["first_sale_day"].isna().sum()),
            "prices": price_missing_summary(stats),
        },
        "selection": selection,
        "selected_items": selected[
            ["item_id", "dept_id", "tier", "mean_units", "zero_share", "price_coverage"]
        ]
        .round(4)
        .to_dict(orient="records"),
        "status": "split (T-09) and selection criteria (T-03) approved 2026-11-23",
    }
    return report, stats


def write_report(report: dict, stats: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Write the JSON report and the per-item statistics (aggregates only)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "inspection_report.json"
    stats_path = out_dir / "item_stats_train.csv"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    stats.round(4).to_csv(stats_path, index=False)
    return [report_path, stats_path]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Command-line options; the store id comes from --store-id or STORE_ID."""
    defaults = SelectionParams()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/inspection"))
    parser.add_argument("--store-id", default=os.environ.get("STORE_ID"))
    parser.add_argument("--n-items", type=int, default=defaults.n_items)
    parser.add_argument("--min-history-days", type=int, default=defaults.min_history_days)
    parser.add_argument("--max-zero-share", type=float, default=defaults.max_zero_share)
    parser.add_argument("--min-price-coverage", type=float, default=defaults.min_price_coverage)
    args = parser.parse_args(argv)
    if not args.store_id:
        parser.error("store id is required: pass --store-id or set STORE_ID")
    return args


def main(argv: list[str] | None = None) -> int:
    """Entry point: inspect, write the report, print a short summary."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    params = SelectionParams(
        n_items=args.n_items,
        min_history_days=args.min_history_days,
        max_zero_share=args.max_zero_share,
        min_price_coverage=args.min_price_coverage,
    )
    try:
        report, stats = inspect(args.raw_dir, args.store_id, params)
    except InspectionError as exc:
        logger.error("%s", exc)
        return 1
    for path in write_report(report, stats, args.out_dir):
        logger.info("Wrote %s", path)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "calendar",
                    "sales_files_comparison",
                    "split",
                    "selection",
                )
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
