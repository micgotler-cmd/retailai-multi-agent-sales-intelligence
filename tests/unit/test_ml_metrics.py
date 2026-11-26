"""Tests for MAE and RMSE against hand-computed values and for unsafe inputs."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.ml import metrics
from src.ml.metrics import MetricsError, score_forecast

GROUPS = {"A": "high", "B": "low"}


def tables(pred_a=(1, 7), act_a=(2, 4), pred_b=(0, 2), act_b=(0, 0)):
    days = pd.to_datetime(["2016-04-25", "2016-04-26"])
    forecast = pd.DataFrame(
        {
            "item_id": ["A", "A", "B", "B"],
            "forecast_date": list(days) * 2,
            "predicted_units": [*pred_a, *pred_b],
        }
    )
    actual = pd.DataFrame(
        {
            "item_id": ["A", "A", "B", "B"],
            "date": list(days) * 2,
            "units_sold": [*act_a, *act_b],
        }
    )
    return forecast, actual


def test_mae_and_rmse_match_hand_computation():
    # item A errors [1, 3]; item B errors [0, 2]; all four errors [1, 3, 0, 2]
    scores = score_forecast(*tables(), GROUPS)
    assert scores["overall"]["mae"] == pytest.approx(1.5)
    assert scores["overall"]["rmse"] == pytest.approx(math.sqrt(3.5), abs=1e-6)
    assert scores["per_item"]["A"]["mae"] == pytest.approx(2.0)
    assert scores["per_item"]["A"]["rmse"] == pytest.approx(math.sqrt(5), abs=1e-6)
    assert scores["per_item"]["B"]["mae"] == pytest.approx(1.0)
    assert scores["per_item"]["B"]["rmse"] == pytest.approx(math.sqrt(2), abs=1e-6)
    assert scores["per_demand_group"]["high"]["mae"] == pytest.approx(2.0)
    assert scores["per_demand_group"]["low"]["rmse"] == pytest.approx(math.sqrt(2), abs=1e-6)
    assert scores["n_item_days"] == 4
    assert scores["per_item"]["A"]["demand_group"] == "high"


def test_perfect_forecast_scores_zero():
    scores = score_forecast(*tables(pred_a=(2, 4), pred_b=(0, 0)), GROUPS)
    assert scores["overall"] == {"mae": 0.0, "rmse": 0.0}


def test_plain_functions():
    actual, predicted = np.array([1.0, 5.0]), np.array([2.0, 3.0])
    assert metrics.mae(actual, predicted) == pytest.approx(1.5)
    assert metrics.rmse(actual, predicted) == pytest.approx(math.sqrt(2.5))


def test_demand_group_with_no_items_is_left_out():
    scores = score_forecast(*tables(), {"A": "high", "B": "high"})
    assert list(scores["per_demand_group"]) == ["high"]
    assert scores["per_demand_group"]["high"]["n_items"] == 2


def test_different_item_days_fail():
    forecast, actual = tables()
    with pytest.raises(MetricsError, match="different item-days"):
        score_forecast(forecast.iloc[:-1], actual, GROUPS)
    with pytest.raises(MetricsError, match="different item-days"):
        score_forecast(forecast, actual.iloc[:-1], GROUPS)


def test_duplicate_item_days_fail():
    forecast, actual = tables()
    with pytest.raises(MetricsError, match="duplicate"):
        score_forecast(pd.concat([forecast, forecast.iloc[[0]]]), actual, GROUPS)


def test_missing_or_infinite_values_fail():
    for bad in (np.nan, np.inf):
        forecast, actual = tables(pred_a=(bad, 7))
        with pytest.raises(MetricsError, match="non-finite"):
            score_forecast(forecast, actual, GROUPS)


def test_item_without_demand_group_fails():
    with pytest.raises(MetricsError, match="demand group"):
        score_forecast(*tables(), {"A": "high"})


def test_missing_columns_and_empty_input_fail():
    forecast, actual = tables()
    with pytest.raises(MetricsError, match="missing columns"):
        score_forecast(forecast.drop(columns="predicted_units"), actual, GROUPS)
    with pytest.raises(MetricsError, match="Nothing to score"):
        score_forecast(forecast.iloc[0:0], actual.iloc[0:0], GROUPS)


def test_mean_of_windows():
    one = {"overall": {"mae": 1.0, "rmse": 2.0}}
    two = {"overall": {"mae": 3.0, "rmse": 4.0}}
    assert metrics.mean_of_windows([one, two]) == {"mae": 2.0, "rmse": 3.0}
    with pytest.raises(MetricsError):
        metrics.mean_of_windows([])
