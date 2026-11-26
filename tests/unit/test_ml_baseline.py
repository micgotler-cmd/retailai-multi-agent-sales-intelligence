"""Tests for the Seasonal Naive baseline: values, history rules and leakage."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.baseline import HistoryError, consecutive_valid_days, seasonal_naive
from tests.ml_data import day_date, make_clean, one_item

ITEM = "FOODS_1_001"


def forecast(history: pd.DataFrame, origin_day: int, horizon: int = 28, items=(ITEM,)):
    return seasonal_naive(history, day_date(origin_day), horizon, list(items))


def test_repeats_the_last_seven_days_four_times():
    values = list(range(10, 60))  # day d has value 9 + d
    history = one_item(values)
    result = forecast(history, origin_day=50)
    last_week = [values[i] for i in range(43, 50)]  # days 44..50
    assert result["predicted_units"].tolist() == last_week * 4
    assert result["forecast_date"].iloc[0] == day_date(51)
    assert result["forecast_date"].iloc[-1] == day_date(78)
    assert len(result) == 28


def test_each_weekday_gets_its_own_last_observed_value():
    history = one_item(list(range(1, 51)))
    result = forecast(history, origin_day=50).set_index("forecast_date")["predicted_units"]
    for step in range(28):
        target = day_date(51 + step)
        same_weekday_last_seen = max(
            d for d in range(44, 51) if day_date(d).weekday() == target.weekday()
        )
        assert result[target] == float(same_weekday_last_seen)  # value equals the day number


def test_exactly_seven_days_of_history_is_enough():
    history = one_item([5, 6, 7, 8, 9, 10, 11])
    result = forecast(history, origin_day=7)
    assert result["predicted_units"].tolist()[:7] == [5, 6, 7, 8, 9, 10, 11]


def test_six_days_of_history_fails_with_item_origin_and_available_days():
    history = one_item([1, 2, 3, 4, 5, 6])
    with pytest.raises(HistoryError) as error:
        forecast(history, origin_day=6)
    message = str(error.value)
    assert ITEM in message
    assert str(day_date(6).date()) in message
    assert "6 consecutive" in message


def test_zero_sales_days_are_valid_observations():
    history = one_item([0] * 20)
    result = forecast(history, origin_day=20)
    assert result["predicted_units"].eq(0.0).all()
    assert consecutive_valid_days(history, day_date(20)) == 20


def test_missing_date_inside_the_last_seven_days_fails():
    history = one_item(list(range(1, 31)))
    history = history[history["date"] != day_date(27)]  # a hole inside days 24..30
    with pytest.raises(HistoryError, match="3 consecutive"):
        forecast(history, origin_day=30)


def test_missing_or_negative_value_in_the_last_seven_days_fails():
    for bad in (np.nan, -1):
        values = [float(v) for v in range(1, 31)]
        values[27] = bad  # day 28
        with pytest.raises(HistoryError, match="2 consecutive"):
            forecast(one_item(values), origin_day=30)


def test_a_gap_older_than_seven_days_does_not_matter():
    history = one_item(list(range(1, 31)))
    history = history[history["date"] != day_date(5)]
    assert len(forecast(history, origin_day=30)) == 28


def test_no_data_at_the_origin_fails():
    history = one_item(list(range(1, 21)))  # data ends before the origin
    with pytest.raises(HistoryError, match="0 consecutive"):
        forecast(history, origin_day=25)


def test_item_without_rows_fails_and_nothing_is_replaced():
    history = one_item(list(range(1, 31)))
    with pytest.raises(HistoryError, match="FOODS_9_999"):
        forecast(history, origin_day=30, items=(ITEM, "FOODS_9_999"))


def test_duplicate_dates_and_mixed_stores_fail():
    history = one_item(list(range(1, 31)))
    with pytest.raises(HistoryError, match="duplicate"):
        forecast(pd.concat([history, history.iloc[[5]]]), origin_day=30)
    other_store = history.copy()
    other_store.loc[other_store.index[-1], "store_id"] = "TX_1"
    with pytest.raises(HistoryError, match="one store"):
        forecast(other_store, origin_day=30)


def test_missing_columns_and_bad_horizon_fail():
    with pytest.raises(HistoryError, match="missing columns"):
        forecast(one_item([1] * 10).drop(columns="units_sold"), origin_day=10)
    with pytest.raises(HistoryError, match="horizon"):
        forecast(one_item([1] * 10), origin_day=10, horizon=0)


def test_leakage_values_after_the_origin_never_change_the_forecast():
    history = make_clean(items=[ITEM], n_days=120)
    origin_day = 80
    baseline_result = forecast(history, origin_day)
    changed = history.copy()
    later = changed["date"] > day_date(origin_day)
    changed.loc[later, "units_sold"] = 10_000  # absurd values inside the forecast window
    pd.testing.assert_frame_equal(baseline_result, forecast(changed, origin_day))
    pd.testing.assert_frame_equal(baseline_result, forecast(history[~later], origin_day))


def test_same_input_gives_identical_output():
    history = make_clean(items=[ITEM], n_days=60)
    pd.testing.assert_frame_equal(forecast(history, 50), forecast(history, 50))
