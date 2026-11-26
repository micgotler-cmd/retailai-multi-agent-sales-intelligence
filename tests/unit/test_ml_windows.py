"""Tests for the forecast windows (T-22, T-23), including the real approved scope."""

from __future__ import annotations

import itertools

import pytest

from src.data.scope import load_scope, parse_scope
from src.ml import windows
from src.ml.windows import ForecastWindow, WindowError
from tests.conftest import make_scope, scope_dict


def test_real_scope_matches_the_approved_backtest_dates():
    scope = load_scope()
    found = [(w.origin_day, w.first_day, w.last_day) for w in windows.backtest_windows(scope)]
    assert found == [(1829, 1830, 1857), (1857, 1858, 1885), (1885, 1886, 1913)]


def test_real_scope_test_and_future_windows():
    scope = load_scope()
    test = windows.final_test_window(scope)
    future = windows.future_window(scope)
    assert (test.origin_day, test.first_day, test.last_day) == (1913, 1914, 1941)
    assert (future.origin_day, future.first_day, future.last_day) == (1941, 1942, 1969)


def test_backtest_never_reaches_the_test_period_and_is_contiguous():
    scope = load_scope()
    backtest = windows.backtest_windows(scope)
    assert max(w.last_day for w in backtest) < scope.split["test"].first_day
    assert all(w.n_days == scope.horizon_days for w in backtest)
    for before, after in itertools.pairwise(backtest):
        assert after.first_day == before.last_day + 1
    assert backtest[-1].last_day == scope.split["validation"].last_day


def test_synthetic_scope_gives_three_windows():
    assert len(windows.backtest_windows(make_scope())) == windows.N_BACKTEST_WINDOWS


def test_too_short_history_is_rejected():
    short = parse_scope(scope_dict(last_day=70))  # first backtest origin would be before day 1
    with pytest.raises(WindowError, match="no history before its origin"):
        windows.backtest_windows(short)


def test_a_window_reaching_the_test_period_is_rejected():
    scope = make_scope()
    test_first = scope.split["test"].first_day
    bad = [ForecastWindow("backtest_1", test_first - 10, test_first + 17)]
    with pytest.raises(WindowError, match="reaches the test period"):
        windows._check_backtest(bad, scope)


def test_non_consecutive_windows_are_rejected():
    scope = make_scope()
    bad = [ForecastWindow("a", 20, 47), ForecastWindow("b", 60, 87)]
    with pytest.raises(WindowError, match="consecutive"):
        windows._check_backtest(bad, scope)
