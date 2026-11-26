"""Forecast windows for the baseline and the models (T-22, T-23).

All windows are derived from the approved scope (`config/data_scope.json`), so
the dates live in one place:

- three non-overlapping backtest windows ending at the end of the validation
  period (model comparison and tuning only, T-23),
- the test window (final evaluation only, T-09),
- the future window right after the test window (dashboard and Agent 7, T-22).

A window's origin is the last observed day before it. Nothing from a window or
later may influence a forecast for that window.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from src.data.scope import DataScope

N_BACKTEST_WINDOWS = 3


class WindowError(Exception):
    """Raised when the windows would break the leakage rules."""


@dataclass(frozen=True)
class ForecastWindow:
    """An inclusive range of M5 day numbers to forecast, with its origin."""

    name: str
    first_day: int
    last_day: int

    @property
    def origin_day(self) -> int:
        """The last observed day before the window."""
        return self.first_day - 1

    @property
    def n_days(self) -> int:
        """Number of days in the window."""
        return self.last_day - self.first_day + 1


def backtest_windows(scope: DataScope) -> list[ForecastWindow]:
    """Three consecutive horizon-length windows, the last one equal to the validation period."""
    horizon = scope.horizon_days
    validation_last = scope.split["validation"].last_day
    windows = []
    for k in range(N_BACKTEST_WINDOWS):
        last = validation_last - (N_BACKTEST_WINDOWS - 1 - k) * horizon
        windows.append(ForecastWindow(f"backtest_{k + 1}", last - horizon + 1, last))
    _check_backtest(windows, scope)
    return windows


def final_test_window(scope: DataScope) -> ForecastWindow:
    """The final 28-day test window (T-09)."""
    part = scope.split["test"]
    return ForecastWindow("test", part.first_day, part.last_day)


def future_window(scope: DataScope) -> ForecastWindow:
    """The horizon right after the last observed day (T-22)."""
    first = scope.last_day + 1
    return ForecastWindow("future", first, first + scope.horizon_days - 1)


def _check_backtest(windows: list[ForecastWindow], scope: DataScope) -> None:
    """Backtest windows are contiguous, in order, before the test window and have a past."""
    test_first = scope.split["test"].first_day
    for window in windows:
        if window.origin_day < 1:
            raise WindowError(f"Window {window.name} has no history before its origin")
        if window.last_day >= test_first:
            raise WindowError(f"Window {window.name} reaches the test period (day {test_first})")
    for before, after in itertools.pairwise(windows):
        if after.first_day != before.last_day + 1:
            raise WindowError(f"Windows {before.name} and {after.name} must be consecutive")
