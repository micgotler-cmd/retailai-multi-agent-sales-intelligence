"""Tests for the EDA facts, report and insights (synthetic clean data only)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data import eda
from src.data.cleaning import CLEAN_COLUMNS
from tests.conftest import make_scope

N = 200  # days; train = 1..144 (2011-10-01 .. 2012-02-21), then validation and test
START = pd.Timestamp("2011-10-01")
TRAIN_LAST = START + pd.Timedelta(days=143)
# item -> (category, base units on open days)
ITEMS = {
    "FOODS_1_001": ("FOODS", 2),
    "FOODS_1_002": ("FOODS", 4),
    "HOUSEHOLD_1_001": ("HOUSEHOLD", 1),
}


def make_clean(sunday_extra: int = 0, snap_extra: int = 0, later_units: int | None = None):
    """Clean data with exactly known values.

    Units = base (+ sunday_extra on Sundays, + snap_extra on SNAP days); SNAP on
    days 1-10 of each month; 25 December closed (0 units); FOODS_1_001's price
    rises from 2.00 to 2.50 in week 5. later_units overrides validation/test days.
    """
    dates = pd.date_range(START, periods=N, freq="D")
    frames = []
    for item, (cat, base) in ITEMS.items():
        units = np.full(N, base)
        units = units + np.where(dates.day_of_week == 6, sunday_extra, 0)
        snap = (dates.day <= 10).astype(int)
        units = units + snap * snap_extra
        closed = ((dates.month == 12) & (dates.day == 25)).astype(int)
        units = np.where(closed == 1, 0, units)
        if later_units is not None:
            units = np.where(dates > TRAIN_LAST, later_units, units)
        week = np.arange(N) // 7
        price = np.where((item == "FOODS_1_001") & (week >= 4), 2.5, 2.0)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "store_id": "CA_1",
                    "item_id": item,
                    "dept_id": item.rsplit("_", 1)[0],
                    "cat_id": cat,
                    "state_id": "CA",
                    "units_sold": units,
                    "sell_price": price,
                    "wm_yr_wk": 11101 + week,
                    "event_name_1": np.where(
                        dates == pd.Timestamp("2011-10-31"), "Halloween", None
                    ),
                    "event_type_1": np.where(dates == pd.Timestamp("2011-10-31"), "Cultural", None),
                    "snap": snap,
                    "store_closed": closed,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)[CLEAN_COLUMNS]


SCOPE = make_scope(items=list(ITEMS), last_day=N)


def facts(result: eda.EDAResult) -> dict[str, dict]:
    return {f["id"]: f for f in result.summary["facts"]}


def value(result: eda.EDAResult, section: str, *path: str):
    ids = result.summary["sections"][section]
    for key in path:
        ids = ids[key]
    return facts(result)[ids]["value"]


@pytest.fixture
def result() -> eda.EDAResult:
    return eda.run_eda(make_clean(sunday_extra=2, snap_extra=1), SCOPE)


# ------------------------------------------------------- training-period boundary


def test_train_last_date_is_d_1885_equivalent():
    assert eda.train_last_date(make_clean(), SCOPE) == TRAIN_LAST


def test_only_training_rows_are_used():
    train = eda.training_rows(make_clean(), SCOPE)
    assert train["date"].max() == TRAIN_LAST
    assert len(train) == 144 * len(ITEMS)


def test_validation_and_test_days_do_not_change_any_fact():
    """Leakage check: extreme values after the training period change nothing."""
    base = eda.run_eda(make_clean(sunday_extra=2, snap_extra=1), SCOPE)
    changed = eda.run_eda(make_clean(sunday_extra=2, snap_extra=1, later_units=999), SCOPE)
    assert base.summary == changed.summary
    assert base.insights == changed.insights


def test_period_is_reported(result):
    period = result.summary["period"]
    assert (period["first_date"], period["last_date"]) == ("2011-10-01", "2012-02-21")
    assert value(result, "overview", "last_date") == "2012-02-21"


# ------------------------------------------------------ key statistics by hand


def test_overview_counts():
    r = eda.run_eda(make_clean(), SCOPE)  # constant units: 2, 4 and 1 per open day
    assert value(r, "overview", "items") == 3
    assert value(r, "overview", "item_days") == 432
    assert value(r, "overview", "closed") == 1  # 25 December 2011
    assert value(r, "overview", "total_units") == (2 + 4 + 1) * 143  # 143 open days each
    assert value(r, "overview", "avg") == pytest.approx(7 * 143 / 432, abs=1e-4)


def test_category_metrics_are_normalized_per_item():
    r = eda.run_eda(make_clean(), SCOPE)
    assert value(r, "category", "FOODS", "items") == 2
    assert value(r, "category", "FOODS", "avg") == 3.0  # (2 + 4) / 2, not the total 6
    assert value(r, "category", "HOUSEHOLD", "avg") == 1.0
    assert value(r, "category", "FOODS", "share") == pytest.approx(600 / 7, abs=1e-3)
    assert value(r, "category", "FOODS", "zero") == 0.0  # closure day excluded


def test_demand_group_metrics():
    scope = make_scope(items=list(ITEMS), last_day=N)
    object.__setattr__(
        scope, "items", {"FOODS_1_001": "medium", "FOODS_1_002": "high", "HOUSEHOLD_1_001": "low"}
    )
    r = eda.run_eda(make_clean(), scope)
    assert value(r, "demand_group", "high", "avg") == 4.0
    assert value(r, "demand_group", "low", "avg") == 1.0
    assert list(r.summary["sections"]["demand_group"]) == ["high", "medium", "low"]


def test_weekday_pattern(result):
    # Sundays: base + 2; other days: base. Mean over items of base = 7/3.
    assert value(result, "weekday", "peak") == "Sunday"
    assert value(result, "weekday", "peak_avg") > value(result, "weekday", "trough_avg")
    sunday = result.summary["tables"]["weekday"]["Sunday"]
    monday = result.summary["tables"]["weekday"]["Monday"]
    assert sunday - monday == pytest.approx(2.0, abs=0.35)  # SNAP mix differs slightly by day


def test_snap_comparison_is_exact_without_other_effects():
    r = eda.run_eda(make_clean(snap_extra=1), SCOPE)
    with_snap, without = value(r, "snap", "all", "with"), value(r, "snap", "all", "without")
    assert with_snap - without == pytest.approx(1.0)
    assert value(r, "snap", "all", "diff") == pytest.approx((with_snap / without - 1) * 100, 1e-3)
    assert "FOODS" in r.summary["sections"]["snap"]  # also per category


def test_event_types_compared_with_no_event_days():
    r = eda.run_eda(make_clean(), SCOPE)  # one Cultural day (Halloween), constant units
    ids = r.summary["sections"]["event_types"]
    assert list(ids) == ["Cultural"]
    assert facts(r)[ids["Cultural"]["days"]]["value"] == 1
    assert facts(r)[ids["Cultural"]["diff"]]["value"] == pytest.approx(0.0)
    table = r.summary["tables"]["event_types"]
    assert [row["event_type"] for row in table] == ["no event", "Cultural"]


def test_closure_days_excluded_from_patterns():
    r = eda.run_eda(make_clean(), SCOPE)
    december = r.summary["tables"]["month"]["Dec"]
    assert december == pytest.approx(7 / 3, abs=1e-4)  # the 0-unit closure day would pull this down


def test_price_changes():
    r = eda.run_eda(make_clean(), SCOPE)
    assert value(r, "price", "changed") == 1
    assert value(r, "price", "max_range_item") == "FOODS_1_001"
    assert value(r, "price", "max_range") == pytest.approx(25.0)


def test_item_trend_and_top_item():
    r = eda.run_eda(make_clean(), SCOPE)
    assert value(r, "items", "top_item") == "FOODS_1_002"
    assert value(r, "items", "top_avg") == 4.0


def test_pct_diff():
    assert eda.pct_diff(3, 2) == 50.0
    assert np.isnan(eda.pct_diff(1, 0))


# ------------------------------------------------------------- traceability


def test_fact_ids_are_unique_and_sequential(result):
    ids = [f["id"] for f in result.summary["facts"]]
    assert ids == [f"F{i:02d}" for i in range(1, len(ids) + 1)]
    for f in result.summary["facts"]:
        assert f["definition"] and f["unit"]


def test_every_number_in_insights_is_a_cited_fact(result):
    known = facts(result)
    pairs = re.findall(r"(\S+) \[(F\d{2,})\]", result.insights)
    assert pairs, "insights should cite facts"
    for shown, fact_id in pairs:
        fact = known[fact_id]
        assert shown.strip("(,;:)") == eda.fmt(fact["value"], fact["unit"]), fact_id
    # Remove cited values, dates, decision ids and fixed method constants: no number may remain.
    rest = re.sub(r"\S+ \[F\d{2,}\]", "", result.insights)
    # Store and item ids (CA_1, FOODS_3_234) and the dataset name M5 are names, not statistics.
    rest = re.sub(
        r"\d{4}-\d{2}-\d{2}|T-\d+|\b365\b|25 December|\b[A-Z]+(?:_\d+)+\b|\bM5\b", "", rest
    )
    assert not re.search(r"\d", rest), rest


def test_associations_are_not_causal(result):
    assert "not causal" in result.insights
    assert "not causal" in result.html
    assert "not treated as promotions" in result.insights


# ------------------------------------------------------------------- outputs


def test_report_is_self_contained_with_eight_charts(result):
    page = result.html
    assert page.count("<img ") == 8
    assert page.count("data:image/png;base64,") == 8
    assert "<script" not in page and "http://" not in page and "https://" not in page


def test_report_has_no_daily_rows(result):
    """Only aggregate tables: no table row starts with a date (T-04)."""
    assert not re.search(r"<tr><td>\d{4}-\d{2}-\d{2}", result.html)


def test_outputs_are_deterministic(tmp_path: Path):
    first = eda.write_outputs(eda.run_eda(make_clean(2, 1), SCOPE), tmp_path / "a")
    second = eda.write_outputs(eda.run_eda(make_clean(2, 1), SCOPE), tmp_path / "b")
    for a, b in zip(first, second, strict=True):
        assert a.read_bytes() == b.read_bytes(), a.name
    assert json.loads(first[0].read_text(encoding="utf-8"))["schema_version"] == "1.0.0"


# ------------------------------------------------------------------ failures


def test_missing_column_fails(tmp_path: Path):
    path = tmp_path / "clean.csv"
    make_clean().drop(columns=["snap"]).to_csv(path, index=False)
    with pytest.raises(eda.EDAError, match="snap"):
        eda.load_clean(path)


def test_missing_file_fails(tmp_path: Path):
    with pytest.raises(eda.EDAError, match="not found"):
        eda.load_clean(tmp_path / "none.csv")


def test_empty_data_fails():
    with pytest.raises(eda.EDAError, match="empty"):
        eda.run_eda(make_clean().iloc[0:0], SCOPE)


def test_no_training_rows_fails():
    late = make_clean()
    late = late[late["date"] > TRAIN_LAST - pd.Timedelta(days=200)]
    late = late[late["date"] > TRAIN_LAST]
    with pytest.raises(eda.EDAError, match="No rows in the training period"):
        eda.run_eda(late, SCOPE)


def test_item_outside_scope_fails():
    scope = make_scope(items=["FOODS_1_001", "FOODS_1_002"], last_day=N)
    with pytest.raises(eda.EDAError, match="HOUSEHOLD_1_001"):
        eda.run_eda(make_clean(), scope)


def test_main_writes_three_files(tmp_path: Path):
    clean_path = tmp_path / "clean.csv"
    make_clean(2, 1).to_csv(clean_path, index=False, date_format="%Y-%m-%d")
    scope_path = tmp_path / "scope.json"
    from tests.conftest import scope_dict

    scope_path.write_text(json.dumps(scope_dict(items=list(ITEMS), last_day=N)), encoding="utf-8")
    out = tmp_path / "eda"
    args = ["--clean", str(clean_path), "--scope", str(scope_path), "--out-dir", str(out)]
    assert eda.main(args) == 0
    assert {p.name for p in out.iterdir()} == {"eda_summary.json", "eda_report.html", "insights.md"}
    assert eda.main(["--clean", str(tmp_path / "none.csv"), "--scope", str(scope_path)]) == 1
