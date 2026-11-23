"""Tests for the wide-to-long ETL, on synthetic M5-shaped files only."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data import etl
from src.data.m5_files import M5DataError
from tests.conftest import ITEMS, N_DAYS, STORE, make_scope


@pytest.fixture
def long(m5_raw_dir: Path) -> pd.DataFrame:
    return etl.build_long_table(m5_raw_dir, make_scope())


def rewrite(path: Path, change) -> None:
    df = pd.read_csv(path)
    out = change(df)
    (out if out is not None else df).to_csv(path, index=False)


def test_columns_match_spec(long: pd.DataFrame):
    assert list(long.columns) == etl.OUTPUT_COLUMNS


def test_one_row_per_item_and_day(long: pd.DataFrame):
    assert len(long) == len(ITEMS) * N_DAYS
    assert not long.duplicated(subset=etl.KEYS).any()
    assert set(long["item_id"]) == set(ITEMS)
    assert set(long["store_id"]) == {STORE}  # the TX_1 rows are excluded


def test_sorted_by_item_then_date(long: pd.DataFrame):
    expected = long.sort_values(["item_id", "date"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(long, expected)


def test_no_days_after_split(m5_raw_dir: Path):
    scope = make_scope(last_day=N_DAYS - 28)
    long = etl.build_long_table(m5_raw_dir, scope)
    assert long["date"].nunique() == N_DAYS - 28
    assert long["date"].max() == pd.Timestamp("2011-01-29") + pd.Timedelta(days=N_DAYS - 29)


def test_units_match_wide_source(m5_raw_dir: Path, long: pd.DataFrame):
    wide = pd.read_csv(m5_raw_dir / "sales_train_evaluation.csv")
    row = wide[(wide["store_id"] == STORE) & (wide["item_id"] == "HOBBIES_1_001")].iloc[0]
    item = long[long["item_id"] == "HOBBIES_1_001"].reset_index(drop=True)
    assert item["units_sold"].tolist() == [int(row[f"d_{d}"]) for d in range(1, N_DAYS + 1)]
    assert item["units_sold"].dtype == "int64"


def test_calendar_join(long: pd.DataFrame):
    first = long[long["item_id"] == ITEMS[0]].iloc[0]
    assert first["date"] == pd.Timestamp("2011-01-29")
    assert first["wm_yr_wk"] == 11101
    event = long[long["date"] == pd.Timestamp("2011-02-06")].iloc[0]
    assert (event["event_name_1"], event["event_type_1"]) == ("SuperBowl", "Sporting")
    assert long["event_name_1"].isna().sum() == len(long) - len(ITEMS)


def test_snap_column_follows_store_state(long: pd.DataFrame):
    days = long[long["item_id"] == ITEMS[0]].set_index("date")["snap"]
    assert days[pd.Timestamp("2011-02-05")] == 1  # CA SNAP day (day of month <= 10)
    assert days[pd.Timestamp("2011-02-12")] == 0  # TX SNAP day, not CA


def test_price_join_uses_the_right_week(m5_raw_dir: Path):
    def change(df):
        mask = (df["item_id"] == ITEMS[0]) & (df["store_id"] == STORE)
        df.loc[mask, "sell_price"] = 1.0 + (df.loc[mask, "wm_yr_wk"] - 11101) / 100
        return df

    rewrite(m5_raw_dir / "sell_prices.csv", change)
    long = etl.build_long_table(m5_raw_dir, make_scope())
    item = long[long["item_id"] == ITEMS[0]]
    expected = 1.0 + (item["wm_yr_wk"] - 11101) / 100
    assert item["sell_price"].round(6).tolist() == expected.round(6).tolist()


def test_missing_prices_stay_null(m5_raw_dir: Path):
    long = etl.build_long_table(m5_raw_dir, make_scope(items=ITEMS + ["HOBBIES_1_004"]))
    item = long[long["item_id"] == "HOBBIES_1_004"]
    weeks_missing = item.loc[item["sell_price"].isna(), "wm_yr_wk"]
    assert len(weeks_missing) > 0
    assert ((weeks_missing - 11101) % 2 == 1).all()  # the fixture removes every second week
    assert long.loc[long["item_id"] != "HOBBIES_1_004", "sell_price"].notna().all()


def test_write_long_table(long: pd.DataFrame, tmp_path: Path):
    path = etl.write_long_table(long, tmp_path / "etl" / "long_data.csv")
    saved = pd.read_csv(path)
    assert list(saved.columns) == etl.OUTPUT_COLUMNS
    assert saved.loc[0, "date"] == "2011-01-29"
    assert len(saved) == len(long)


# -------------------------------------------------------------- failures


def test_missing_approved_item_fails(m5_raw_dir: Path):
    with pytest.raises(M5DataError, match="FOODS_9_999"):
        etl.build_long_table(m5_raw_dir, make_scope(items=ITEMS + ["FOODS_9_999"]))


def test_missing_calendar_column_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "calendar.csv", lambda df: df.drop(columns=["event_type_1"]))
    with pytest.raises(M5DataError, match="event_type_1"):
        etl.build_long_table(m5_raw_dir, make_scope())


def test_missing_snap_column_for_state_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "calendar.csv", lambda df: df.drop(columns=["snap_CA"]))
    with pytest.raises(M5DataError, match="snap_CA"):
        etl.build_long_table(m5_raw_dir, make_scope())


def test_sales_shorter_than_split_fails(m5_raw_dir: Path):
    with pytest.raises(M5DataError, match="split needs"):
        etl.build_long_table(m5_raw_dir, make_scope(last_day=N_DAYS + 28))


def test_day_missing_from_calendar_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "calendar.csv", lambda df: df[df["d"] != "d_50"])
    with pytest.raises(M5DataError, match="d_50"):
        etl.build_long_table(m5_raw_dir, make_scope())


def test_duplicate_price_key_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "sell_prices.csv", lambda df: pd.concat([df, df.iloc[[0]]]))
    with pytest.raises(M5DataError, match="duplicate"):
        etl.build_long_table(m5_raw_dir, make_scope())


def test_duplicate_sales_row_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "sales_train_evaluation.csv", lambda df: pd.concat([df, df.iloc[[0]]]))
    with pytest.raises(M5DataError, match="Duplicate"):
        etl.build_long_table(m5_raw_dir, make_scope())


def test_missing_file_fails(m5_raw_dir: Path):
    (m5_raw_dir / "sell_prices.csv").unlink()
    with pytest.raises(M5DataError, match="sell_prices.csv"):
        etl.build_long_table(m5_raw_dir, make_scope())


def test_main_exit_codes(m5_raw_dir: Path, tmp_path: Path):
    out = tmp_path / "long.csv"
    assert etl.main(["--raw-dir", str(tmp_path / "empty"), "--out", str(out)]) == 1
    assert etl.main(["--scope", str(tmp_path / "missing.json")]) == 1
