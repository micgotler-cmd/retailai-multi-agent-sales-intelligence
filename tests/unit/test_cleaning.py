"""Tests for the cleaning rules (T-13), on synthetic data only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data import cleaning as c
from src.data.etl import OUTPUT_COLUMNS
from tests.conftest import ITEMS, STORE, make_scope

N = 200  # days; train = 1..144, validation = 145..172, test = 173..200
START = "2011-10-01"  # so the range contains 25 December 2011


def make_long(first_sale: dict[str, int], start: str = START, n_days: int = N) -> pd.DataFrame:
    """A long table like the ETL output. Item units are 0 before first_sale[item], then 1-3."""
    dates = pd.date_range(start, periods=n_days, freq="D")
    rows = []
    for item, first in first_sale.items():
        units = np.where(np.arange(1, n_days + 1) >= first, 1 + np.arange(n_days) % 3, 0)
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "store_id": STORE,
                    "item_id": item,
                    "dept_id": item.rsplit("_", 1)[0],
                    "cat_id": item.split("_")[0],
                    "state_id": "CA",
                    "units_sold": units,
                    "sell_price": np.where(np.arange(1, n_days + 1) >= first - 3, 2.5, np.nan),
                    "wm_yr_wk": 11101 + np.arange(n_days) // 7,
                    "event_name_1": None,
                    "event_type_1": None,
                    "snap": 0,
                }
            )
        )
    long = pd.concat(rows, ignore_index=True)[OUTPUT_COLUMNS]
    return long.sort_values(["item_id", "date"]).reset_index(drop=True)


FIRST = {"A_1_001": 1, "B_1_002": 30, "C_1_003": 100}


@pytest.fixture
def scope():
    return make_scope(items=list(FIRST), last_day=N)


@pytest.fixture
def cleaned(scope):
    return c.clean(make_long(FIRST), scope)


def test_columns_and_order(cleaned):
    df, _ = cleaned
    assert list(df.columns) == c.CLEAN_COLUMNS
    expected = df.sort_values(["item_id", "date"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(df, expected)


def test_rows_before_first_sale_are_dropped(cleaned):
    df, log = cleaned
    starts = df.groupby("item_id")["date"].min()
    day_1 = pd.Timestamp(START)
    for item, first in FIRST.items():
        assert starts[item] == day_1 + pd.Timedelta(days=first - 1)
    action = log["actions"][0]
    assert action["rows_dropped_per_item"] == {"A_1_001": 0, "B_1_002": 29, "C_1_003": 99}
    assert action["rows_dropped"] == 128
    assert log["rows_in"] - log["rows_out"] == 128


def test_dates_continuous_to_last_day(cleaned):
    df, log = cleaned
    for _, dates in df.groupby("item_id")["date"]:
        assert dates.diff().dropna().eq(pd.Timedelta(days=1)).all()
        assert dates.max() == pd.Timestamp(START) + pd.Timedelta(days=N - 1)
    assert log["last_date"] == "2012-04-17"


def test_first_sale_uses_training_period_only(scope):
    """An item whose first sale is after training fails: test data never sets the start."""
    with pytest.raises(c.CleaningError, match="no sale in the training period"):
        c.clean(make_long({"A_1_001": 1, "Z_1_009": 150}), scope)


def test_later_days_do_not_change_first_sale(scope):
    """Leakage check: changing validation/test units does not move the start date."""
    long = make_long(FIRST)
    before, _ = c.clean(long, scope)
    changed = long.copy()
    late = changed["date"] > pd.Timestamp(START) + pd.Timedelta(days=143)
    changed.loc[late, "units_sold"] = 50
    after, _ = c.clean(changed, scope)
    assert before.groupby("item_id")["date"].min().equals(after.groupby("item_id")["date"].min())


def test_christmas_is_flagged_and_units_unchanged(scope):
    long = make_long(FIRST)
    xmas = long["date"] == pd.Timestamp("2011-12-25")
    long.loc[xmas, "units_sold"] = 0
    df, log = c.clean(long, scope)
    flagged = df[df["store_closed"] == 1]
    assert set(flagged["date"]) == {pd.Timestamp("2011-12-25")}
    assert (flagged["units_sold"] == 0).all()
    assert df["store_closed"].sum() == 2  # A and B are on sale by then, C is not yet
    action = log["actions"][1]
    assert action["dates"] == ["2011-12-25"] and action["flagged_rows_with_sales"] == 0


def test_no_christmas_in_range(scope):
    df, log = c.clean(make_long(FIRST, start="2011-01-29"), scope)
    assert df["store_closed"].sum() == 0
    assert log["actions"][1]["rows_flagged"] == 0


def test_log_is_json_serializable(cleaned, tmp_path: Path):
    df, log = cleaned
    paths = c.write_outputs(df, log, tmp_path / "clean")
    saved = json.loads(paths[1].read_text(encoding="utf-8"))
    assert saved["actions"][2]["missing_prices"] == 0
    assert pd.read_csv(paths[0]).shape == df.shape


# ---------------------------------------------------------------- failures


def test_missing_price_on_selling_day_fails(scope):
    long = make_long(FIRST)
    long.loc[(long["item_id"] == "A_1_001") & (long.index % 40 == 5), "sell_price"] = np.nan
    with pytest.raises(c.CleaningError, match="never imputed"):
        c.clean(long, scope)


def test_non_positive_price_fails(scope):
    long = make_long(FIRST)
    long.loc[long["item_id"] == "A_1_001", "sell_price"] = 0.0
    with pytest.raises(c.CleaningError, match="zero or negative"):
        c.clean(long, scope)


def test_negative_units_fail(scope):
    long = make_long(FIRST)
    long.loc[long.index[150], "units_sold"] = -1
    with pytest.raises(c.CleaningError, match="negative units_sold"):
        c.clean(long, scope)


def test_duplicate_rows_fail(scope):
    long = make_long(FIRST)
    long = pd.concat([long, long.iloc[[150]]]).sort_values(["item_id", "date"])
    with pytest.raises(c.CleaningError):
        c.clean(long, scope)


def test_gap_in_input_fails(scope):
    long = make_long(FIRST)
    long = long[long["date"] != pd.Timestamp(START) + pd.Timedelta(days=50)]
    with pytest.raises(c.CleaningError, match="without gaps"):
        c.clean(long, scope)


def test_item_missing_a_middle_day_fails(scope):
    long = make_long(FIRST)
    gap = (long["item_id"] == "B_1_002") & (long["date"] == pd.Timestamp("2011-12-01"))
    with pytest.raises(c.CleaningError, match="not continuous"):
        c.clean(long[~gap], scope)


# ------------------------------------------------------------- whole pipeline


def test_main_on_raw_fixture(m5_raw_dir: Path, tmp_path: Path):
    """Validation, ETL and cleaning on the synthetic raw files."""
    scope_path = tmp_path / "scope.json"
    s = make_scope(items=ITEMS + ["HOBBIES_1_003"])
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "store_id": s.store_id,
                "sales_file": s.sales_file,
                "horizon_days": 28,
                "split": {
                    p: {"first_day": r.first_day, "last_day": r.last_day}
                    for p, r in s.split.items()
                },
                "items": [{"item_id": i, "demand_group": "high"} for i in s.item_ids],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "clean"
    args = ["--raw-dir", str(m5_raw_dir), "--scope", str(scope_path), "--out-dir", str(out)]
    assert c.main(args) == 0
    df = pd.read_csv(out / "clean_data.csv")
    log = json.loads((out / "cleaning_log.json").read_text(encoding="utf-8"))
    assert log["actions"][0]["rows_dropped_per_item"]["HOBBIES_1_003"] == 120
    assert df["sell_price"].notna().all()
    assert (out / "quality_report.json").is_file()


def test_main_stops_when_validation_fails(m5_raw_dir: Path, tmp_path: Path):
    (m5_raw_dir / "calendar.csv").unlink()
    out = tmp_path / "clean"
    assert c.main(["--raw-dir", str(m5_raw_dir), "--out-dir", str(out)]) == 1
    assert (out / "quality_report.json").is_file()
    assert not (out / "clean_data.csv").exists()
