"""Unit tests for the read-only M5 inspection (synthetic data only)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data import inspect_m5 as im
from tests.conftest import N_DAYS, STORE

# Small-fixture thresholds: 200 days of history, so the 365-day default is too strict.
PARAMS = im.SelectionParams(
    n_items=6, min_history_days=100, max_zero_share=0.8, min_price_coverage=0.95
)
TRAIN_LAST = N_DAYS - 56


@pytest.fixture
def loaded(m5_raw_dir: Path):
    cal = im.load_calendar(m5_raw_dir / "calendar.csv")
    sales = im.load_store_sales(m5_raw_dir / "sales_train_evaluation.csv", STORE, chunksize=5)
    prices = im.load_store_prices(m5_raw_dir / "sell_prices.csv", STORE)
    return cal, sales, prices


@pytest.fixture
def stats(loaded) -> pd.DataFrame:
    cal, sales, prices = loaded
    return im.compute_item_stats(sales, cal, prices, TRAIN_LAST).set_index("item_id")


# -------------------------------------------------------------- file checks


def test_missing_file_raises(m5_raw_dir: Path):
    (m5_raw_dir / "sell_prices.csv").unlink()
    with pytest.raises(im.InspectionError, match="sell_prices.csv"):
        im.check_files(m5_raw_dir)


def test_missing_column_raises():
    with pytest.raises(im.InspectionError, match="sell_price"):
        im.check_columns("sell_prices", ["store_id", "item_id", "wm_yr_wk"])


def test_sales_without_day_columns_raises():
    with pytest.raises(im.InspectionError, match="no day columns"):
        im.check_columns("sales_evaluation", im.REQUIRED_COLUMNS["sales_evaluation"])


def test_unknown_store_raises(m5_raw_dir: Path):
    with pytest.raises(im.InspectionError, match="XX_9"):
        im.load_store_sales(m5_raw_dir / "sales_train_evaluation.csv", "XX_9")


def test_day_columns_sorted_numerically():
    assert im.day_columns(["id", "d_10", "d_2", "d_1"]) == ["d_1", "d_2", "d_10"]


# ---------------------------------------------------------------- summaries


def test_calendar_summary_clean(loaded):
    summary = im.calendar_summary(loaded[0])
    assert summary["first_date"] == "2011-01-29"
    assert summary["missing_dates"] == []
    assert summary["day_ids_contiguous"]


def test_calendar_summary_detects_gap(loaded):
    cal = loaded[0].drop(index=10)
    summary = im.calendar_summary(cal)
    assert summary["missing_dates"] == ["2011-02-08"]
    assert not summary["day_ids_contiguous"]


def test_sales_summary_filters_store(loaded):
    cal, sales, _ = loaded
    summary = im.sales_summary(sales, cal)
    assert summary["items"] == 14
    assert (summary["first_day"], summary["last_day"]) == (1, N_DAYS)
    assert summary["day_columns_contiguous"]
    assert summary["negative_values"] == 0


def test_validation_is_prefix_of_evaluation(m5_raw_dir: Path, loaded):
    val = im.load_store_sales(m5_raw_dir / "sales_train_validation.csv", STORE)
    result = im.compare_sales_files(val, loaded[1])
    assert result["validation_is_prefix_of_evaluation"]
    assert result["evaluation_days"] - result["validation_days"] == 28


def test_compare_detects_changed_history(m5_raw_dir: Path, loaded):
    val = im.load_store_sales(m5_raw_dir / "sales_train_validation.csv", STORE)
    val.loc[0, "d_5"] += 1
    assert not im.compare_sales_files(val, loaded[1])["validation_is_prefix_of_evaluation"]


def test_propose_split_boundaries(loaded):
    split = im.propose_split(N_DAYS, loaded[0])
    assert split["test"] == {
        "first_day": N_DAYS - 27,
        "last_day": N_DAYS,
        "first_date": "2011-07-20",
        "last_date": "2011-08-16",
    }
    assert split["validation"]["last_day"] == N_DAYS - 28
    assert split["train"]["last_day"] == TRAIN_LAST


def test_propose_split_too_short_raises(loaded):
    with pytest.raises(im.InspectionError, match="history"):
        im.propose_split(80, loaded[0])


# ------------------------------------------------------------- item stats


def test_item_stats_hand_computed(stats):
    row = stats.loc["HOBBIES_1_001"]  # 0, 2, 0, 2, ... first sale on day 2
    assert row["first_sale_day"] == 2
    assert row["history_days"] == TRAIN_LAST - 1
    assert row["zero_share"] == pytest.approx((TRAIN_LAST - 1 - TRAIN_LAST // 2) / (TRAIN_LAST - 1))
    assert row["mean_units"] == pytest.approx(2 * (TRAIN_LAST // 2) / (TRAIN_LAST - 1))
    assert row["price_coverage"] == 1.0


def test_item_stats_edge_cases(stats):
    assert stats.loc["HOBBIES_1_003", "first_sale_day"] == 121
    assert stats.loc["HOBBIES_1_003", "history_days"] == TRAIN_LAST - 120
    assert stats.loc["HOBBIES_1_004", "price_coverage"] == pytest.approx(0.5, abs=0.05)
    never = stats.loc["HOBBIES_1_005"]
    assert pd.isna(never["first_sale_day"]) and never["history_days"] == 0


def test_item_stats_ignore_validation_and_test_days(loaded):
    """Leakage check: changing days after the training period changes nothing."""
    cal, sales, prices = loaded
    before = im.compute_item_stats(sales, cal, prices, TRAIN_LAST)
    changed = sales.copy()
    later = [f"d_{d}" for d in range(TRAIN_LAST + 1, N_DAYS + 1)]
    changed[later] = 999
    after = im.compute_item_stats(changed, cal, prices, TRAIN_LAST)
    pd.testing.assert_frame_equal(before, after)


# -------------------------------------------------------------- selection


def test_tier_counts():
    assert im.tier_counts(20) == {"high": 7, "medium": 7, "low": 6}
    assert im.tier_counts(50) == {"high": 17, "medium": 17, "low": 16}


def test_selection_excludes_ineligible_items(stats):
    selected, info = im.select_items(stats.reset_index(), PARAMS)
    excluded = {"HOBBIES_1_002", "HOBBIES_1_003", "HOBBIES_1_004", "HOBBIES_1_005"}
    assert excluded.isdisjoint(info["selected_item_ids"])
    assert len(selected) == 6
    assert selected["tier"].value_counts().to_dict() == {"high": 2, "medium": 2, "low": 2}
    assert info["eligible_items"] == 10


def test_selection_is_reproducible(stats):
    first = im.select_items(stats.reset_index(), PARAMS)[1]["selected_item_ids"]
    second = im.select_items(stats.reset_index(), PARAMS)[1]["selected_item_ids"]
    assert first == second


def test_spread_positions_cover_the_pool():
    assert im.spread_positions(10, 2).tolist() == [2, 7]
    assert im.spread_positions(7, 7).tolist() == list(range(7))
    with pytest.raises(im.InspectionError, match="Cannot pick"):
        im.spread_positions(3, 4)


def test_selection_spreads_over_demand_range():
    """Within each tier the picks span the tier's range instead of clustering."""
    stats = pd.DataFrame(
        {
            "item_id": [f"I_{i:03d}" for i in range(90)],
            "mean_units": np.arange(90, 0, -1, dtype=float),
            "history_days": 500,
            "zero_share": 0.1,
            "price_coverage": 1.0,
        }
    )
    selected, _ = im.select_items(stats, im.SelectionParams(n_items=9))
    high = selected[selected["tier"] == "high"]["mean_units"].tolist()
    assert high == [85.0, 75.0, 65.0]  # midpoints of three slices of 90..61


def test_price_availability_before_first_sale(stats):
    late = stats.loc["HOBBIES_1_003"]  # priced from week 1, first sale on day 121
    assert late["first_price_day"] == 1
    assert late["first_price_week"] < late["first_sale_week"]
    summary = im.price_missing_summary(stats.reset_index())
    assert summary["items_priced_after_first_sale_week"] == 0
    assert summary["items_below_95pct_coverage"] == 1  # HOBBIES_1_004


def test_selection_fails_when_too_few_eligible(stats):
    strict = im.SelectionParams(n_items=6, min_history_days=1000)
    with pytest.raises(im.InspectionError, match="eligible"):
        im.select_items(stats.reset_index(), strict)


# ------------------------------------------------------------------- end to end


def test_main_writes_aggregate_report(m5_raw_dir: Path, tmp_path: Path):
    out = tmp_path / "out"
    code = im.main(
        [
            "--raw-dir",
            str(m5_raw_dir),
            "--out-dir",
            str(out),
            "--store-id",
            STORE,
            "--n-items",
            "6",
            "--min-history-days",
            "100",
        ]
    )
    assert code == 0
    report = json.loads((out / "inspection_report.json").read_text(encoding="utf-8"))
    assert report["store_id"] == STORE
    assert len(report["selection"]["selected_item_ids"]) == 6
    stats = pd.read_csv(out / "item_stats_train.csv")
    assert not any(c.startswith("d_") for c in stats.columns)  # aggregates only, no raw days


def test_main_returns_error_for_missing_data(tmp_path: Path):
    assert im.main(["--raw-dir", str(tmp_path), "--store-id", STORE]) == 1


def test_main_requires_store_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("STORE_ID", raising=False)
    with pytest.raises(SystemExit):
        im.main([])
