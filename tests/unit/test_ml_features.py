"""Tests for the feature schema and builder: values, leakage, history gaps and Gate 2 checks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ml import feature_spec as spec
from src.ml import features as ft
from src.ml.feature_spec import FeatureError
from src.ml.windows import backtest_windows, final_test_window, future_window
from tests.conftest import ITEMS, N_DAYS, make_scope, write_scope_file
from tests.ml_data import day_date, make_calendar, make_clean, with_ids

FUTURE_LAST = N_DAYS + 28
ITEM = ITEMS[0]


@pytest.fixture
def scope():
    return make_scope()


@pytest.fixture
def clean():
    return with_ids(make_clean())


@pytest.fixture
def built(clean, scope):
    return ft.build_features(clean, make_calendar(), scope)


def units(clean: pd.DataFrame, item: str, day: int) -> float:
    rows = clean[(clean["item_id"] == item) & (clean["date"] == day_date(day))]
    return float(rows["units_sold"].iloc[0])


def row(table: pd.DataFrame, item: str, day: int) -> pd.Series:
    return table[(table["item_id"] == item) & (table["day"] == day)].iloc[0]


# --- values -----------------------------------------------------------------------------


def test_lags_and_rolling_values_match_hand_computation(built, clean):
    t = 100
    got = row(built, ITEM, t)
    series = {d: units(clean, ITEM, d) for d in range(1, N_DAYS + 1)}
    assert got["lag_28"] == series[t - 28]
    assert got["lag_35"] == series[t - 35]
    assert got["lag_42"] == series[t - 42]
    last7 = [series[d] for d in range(t - 34, t - 27)]  # t-34 .. t-28
    last28 = [series[d] for d in range(t - 55, t - 27)]  # t-55 .. t-28
    assert got["roll_mean_7"] == pytest.approx(np.mean(last7))
    assert got["roll_mean_28"] == pytest.approx(np.mean(last28))
    assert got["roll_std_28"] == pytest.approx(np.std(last28))
    assert got["units_sold"] == series[t]


def test_calendar_event_and_snap_features(built):
    got = row(built, ITEM, 150)  # d % 50 == 0 and % 10 == 0
    assert got["event_type_1"] == "Sporting" and got["snap"] == 1
    plain = row(built, ITEM, 151)
    assert plain["event_type_1"] == "none" and plain["snap"] == 0
    date = day_date(151)
    assert plain["day_of_week"] == date.day_of_week
    assert plain["month"] == date.month and plain["day_of_month"] == date.day


def test_store_closed_follows_the_25_december_rule():
    dates = pd.Series(pd.to_datetime(["2015-12-24", "2015-12-25", "2016-12-25", "2016-05-25"]))
    assert ft._is_closure(dates).tolist() == [False, True, True, False]


def test_future_days_have_calendar_features_and_no_target(built, scope):
    future = built[built["day"] > scope.last_day]
    assert future["day"].min() == N_DAYS + 1 and future["day"].max() == FUTURE_LAST
    assert future[spec.TARGET_COLUMN].isna().all()
    assert future[spec.FEATURE_COLUMNS].notna().all().all()
    assert len(future) == 28 * len(ITEMS)


# --- leakage ----------------------------------------------------------------------------


def perturb(clean: pd.DataFrame, from_day: int, items=None) -> pd.DataFrame:
    changed = clean.copy()
    mask = changed["date"] >= day_date(from_day)
    if items is not None:
        mask &= changed["item_id"].isin(items)
    changed.loc[mask, "units_sold"] += 1000
    return changed


def test_features_for_day_t_never_read_sales_after_t_minus_28(built, clean, scope):
    cut = 150
    other = ft.build_features(perturb(clean, cut), make_calendar(), scope)
    safe = built["day"] < cut + 28  # their newest input is day t - 28 < cut
    feature_columns = spec.FEATURE_COLUMNS
    pd.testing.assert_frame_equal(
        built.loc[safe, feature_columns].reset_index(drop=True),
        other.loc[safe, feature_columns].reset_index(drop=True),
    )
    assert not built.loc[~safe, spec.HISTORY_FEATURES].equals(
        other.loc[~safe, spec.HISTORY_FEATURES]
    )  # the perturbation is visible beyond the guard, so the test is not vacuous


def test_no_leakage_across_items(built, clean, scope):
    other = ft.build_features(perturb(clean, 1, items=[ITEMS[1]]), make_calendar(), scope)
    keep = built["item_id"] != ITEMS[1]
    pd.testing.assert_frame_equal(
        built[keep].reset_index(drop=True), other[keep].reset_index(drop=True)
    )


def test_training_rows_do_not_depend_on_sales_after_the_origin(built, clean, scope):
    origin = scope.split["validation"].first_day - 1
    other = ft.build_features(perturb(clean, origin + 1), make_calendar(), scope)
    before = ft.training_rows(built, origin)
    after = ft.training_rows(other, origin)
    pd.testing.assert_frame_equal(before, after)
    assert before["day"].max() <= origin


def test_forecast_rows_do_not_depend_on_sales_after_the_origin(built, clean, scope):
    for window in backtest_windows(scope) + [final_test_window(scope)]:
        other = ft.build_features(perturb(clean, window.first_day), make_calendar(), scope)
        pd.testing.assert_frame_equal(
            ft.forecast_rows(built, window), ft.forecast_rows(other, window)
        )


# --- availability for the whole horizon ---------------------------------------------------


def test_features_exist_for_all_28_days_of_every_window(built, scope):
    windows = [*backtest_windows(scope), final_test_window(scope), future_window(scope)]
    for window in windows:
        rows = ft.forecast_rows(built, window)
        assert len(rows) == 28 * len(ITEMS)
        assert rows[spec.FEATURE_COLUMNS].notna().all().all()
        assert spec.TARGET_COLUMN not in rows.columns


def test_forecast_rows_fail_when_a_day_is_missing(built, scope):
    window = final_test_window(scope)
    broken = built[~((built["day"] == window.last_day) & (built["item_id"] == ITEM))]
    with pytest.raises(FeatureError, match="cover every item-day"):
        ft.forecast_rows(broken, window)


# --- missing history ------------------------------------------------------------------------


def test_history_before_the_first_sale_is_left_empty_and_not_trained_on(scope):
    start = 30
    data = with_ids(make_clean())
    late = data[~((data["item_id"] == ITEM) & (data["date"] < day_date(start)))]
    table = ft.build_features(late, make_calendar(), scope)
    item = table[table["item_id"] == ITEM].set_index("day")
    assert item.index.min() == start
    assert item.loc[start : start + 27, "lag_28"].isna().all()  # no imputation
    assert item.loc[start + 28, "lag_28"] == units(late, ITEM, start)
    assert item.loc[start + 28 + 27, "roll_mean_28"] == pytest.approx(
        late[(late["item_id"] == ITEM) & (late["date"] <= day_date(start + 27))]["units_sold"]
        .iloc[:28]
        .mean()
    )
    assert item.loc[: start + 41, "lag_42"].isna().all()
    train = ft.training_rows(table, scope.split["train"].last_day)
    first_trainable = train[train["item_id"] == ITEM]["day"].min()
    assert first_trainable == start + 55 + 0  # roll_mean_28 / roll_std_28 need 28 days
    assert train[spec.FEATURE_COLUMNS].notna().all().all()


def test_zero_sales_days_are_valid(scope):
    data = with_ids(make_clean())
    data.loc[data["item_id"] == ITEM, "units_sold"] = 0
    table = ft.build_features(data, make_calendar(), scope)
    assert row(table, ITEM, 100)["lag_28"] == 0
    assert row(table, ITEM, 100)["roll_std_28"] == 0


def test_a_gap_inside_the_history_is_an_error(clean, scope):
    gap = clean[~((clean["item_id"] == ITEM) & (clean["date"] == day_date(80)))]
    with pytest.raises(FeatureError, match="missing dates"):
        ft.build_features(gap, make_calendar(), scope)


@pytest.mark.parametrize("bad", [np.nan, -1.0])
def test_missing_or_negative_units_are_an_error(clean, scope, bad):
    broken = clean.copy()
    broken.loc[(broken["item_id"] == ITEM) & (broken["date"] == day_date(80)), "units_sold"] = bad
    with pytest.raises(FeatureError, match=ITEM):
        ft.build_features(broken, make_calendar(), scope)


def test_history_that_ends_early_is_an_error(clean, scope):
    short = clean[~((clean["item_id"] == ITEM) & (clean["date"] > day_date(N_DAYS - 1)))]
    with pytest.raises(FeatureError, match="history ends"):
        ft.build_features(short, make_calendar(), scope)


# --- calendar problems --------------------------------------------------------------------------


def test_calendar_that_misses_future_days_is_an_error(clean, scope):
    with pytest.raises(FeatureError, match="does not cover"):
        ft.build_features(clean, make_calendar(FUTURE_LAST - 1), scope)


def test_calendar_with_shifted_day_numbers_is_an_error(clean, scope):
    shifted = make_calendar().assign(day=lambda c: c["day"] + 1)
    with pytest.raises(FeatureError, match="day numbers"):
        ft.build_features(clean, shifted, scope)


# --- separation of features, target and metadata ------------------------------------------------


def test_features_target_and_metadata_are_separate(built):
    assert list(built.columns) == spec.ALL_COLUMNS
    assert spec.TARGET_COLUMN not in spec.FEATURE_COLUMNS
    assert not set(spec.METADATA_COLUMNS) & set(spec.FEATURE_COLUMNS)
    assert set(spec.KEY_COLUMNS) & set(spec.FEATURE_COLUMNS) == {"item_id"}
    assert "demand_group" not in spec.FEATURE_COLUMNS  # group labels use d_1..d_1885 (T-03)
    assert "sell_price" not in built.columns  # D-07
    assert len(spec.FEATURE_COLUMNS) == len(set(spec.FEATURE_COLUMNS))


def test_training_matrix_has_features_only(built, scope):
    rows = ft.training_rows(built, scope.split["train"].last_day)
    assert not rows.empty
    assert rows[spec.FEATURE_COLUMNS].notna().all().all()
    assert rows[spec.TARGET_COLUMN].notna().all()


def test_the_spec_rejects_look_back_shorter_than_the_horizon(monkeypatch):
    spec.check_spec(28)
    with pytest.raises(FeatureError, match="longer than the minimum"):
        spec.check_spec(29)
    monkeypatch.setattr(spec, "LAG_FEATURES", {"lag_7": 7})
    with pytest.raises(FeatureError, match="shorter than the horizon"):
        spec.check_spec(28)


def test_longest_lookback_is_55_days():
    assert spec.longest_lookback() == 55


# --- Gate 2 validation -----------------------------------------------------------------------------


def test_a_valid_table_passes_validation(built, scope):
    spec.validate_features(built, scope)


def test_validation_catches_missing_extra_and_mistyped_columns(built, scope):
    with pytest.raises(FeatureError, match="missing"):
        spec.validate_features(built.drop(columns="lag_28"), scope)
    with pytest.raises(FeatureError, match="extra"):
        spec.validate_features(built.assign(sell_price=1.0), scope)
    with pytest.raises(FeatureError, match="numeric"):
        spec.validate_features(built.assign(lag_28=built["lag_28"].astype(str)), scope)


def test_validation_catches_a_target_in_the_future_and_incomplete_windows(built, scope):
    leaky = built.copy()
    leaky.loc[leaky["day"] == FUTURE_LAST, spec.TARGET_COLUMN] = 1.0
    with pytest.raises(FeatureError, match="future day carries a target"):
        spec.validate_features(leaky, scope)
    holes = built.copy()
    holes.loc[(holes["day"] == N_DAYS + 5) & (holes["item_id"] == ITEM), "lag_42"] = np.nan
    with pytest.raises(FeatureError, match="incomplete features"):
        spec.validate_features(holes, scope)
    with pytest.raises(FeatureError, match="Duplicate"):
        spec.validate_features(pd.concat([built, built.iloc[:1]]), scope)


# --- the command ----------------------------------------------------------------------------------


@pytest.fixture
def cli_inputs(tmp_path, clean):
    clean_path = tmp_path / "clean.csv"
    clean.assign(store_closed=0).to_csv(clean_path, index=False)
    cal = make_calendar().rename(columns={"snap": "snap_CA"}).drop(columns="day")
    cal = cal.assign(event_name_1=None, wm_yr_wk=1)
    cal_path = tmp_path / "calendar.csv"
    cal.to_csv(cal_path, index=False)
    scope_path = write_scope_file(tmp_path / "scope.json")
    return clean_path, cal_path, scope_path


def run_cli(inputs, out: Path) -> int:
    clean_path, cal_path, scope_path = inputs
    return ft.main(
        [
            "--clean-data",
            str(clean_path),
            "--calendar",
            str(cal_path),
            "--scope",
            str(scope_path),
            "--out-dir",
            str(out),
        ]
    )


def test_command_writes_features_and_reruns_identically(cli_inputs, tmp_path):
    out = tmp_path / "out"
    assert run_cli(cli_inputs, out) == 0
    first = (out / ft.FEATURES_FILE).read_bytes()
    assert run_cli(cli_inputs, out) == 0
    assert (out / ft.FEATURES_FILE).read_bytes() == first
    table = ft.read_features(out / ft.FEATURES_FILE)
    spec.validate_features(table, make_scope())
    assert not list(out.glob("*.tmp"))


def test_failed_run_removes_stale_output(cli_inputs, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / ft.FEATURES_FILE).write_text("STALE")
    (out / f"{ft.FEATURES_FILE}.tmp").write_text("STALE")
    _, cal_path, _ = cli_inputs
    cal_path.unlink()
    assert run_cli(cli_inputs, out) == 1
    assert not list(out.iterdir())


def test_default_output_folder_is_ignored_by_git():
    if shutil.which("git") is None:
        pytest.skip("git not available")
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        ["git", "check-ignore", "-q", str(ft.DEFAULT_OUT_DIR / ft.FEATURES_FILE)],
        cwd=root,
        check=False,
    )
    if probe.returncode == 128:
        pytest.skip("not a git repository")
    assert probe.returncode == 0
