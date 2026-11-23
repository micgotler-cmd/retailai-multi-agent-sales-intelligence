"""Tests for the Data Validator logic, on synthetic M5-shaped files only."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data import validation as v
from tests.conftest import ITEMS, N_DAYS, STORE, make_scope


def rewrite(path: Path, change) -> None:
    """Apply change(df) to a CSV in place (change may edit df or return a new frame)."""
    df = pd.read_csv(path)
    out = change(df)
    (out if out is not None else df).to_csv(path, index=False)


def results(raw_dir: Path, scope=None) -> dict[str, v.CheckResult]:
    return {r.name: r for r in v.run_checks(raw_dir, scope or make_scope())}


def report(raw_dir: Path, scope=None) -> dict:
    return v.run_validation(raw_dir, scope or make_scope())


SALES = "sales_train_evaluation.csv"


def set_units(day: int, value, item: str = "FOODS_1_001"):
    def change(df: pd.DataFrame) -> pd.DataFrame:
        df[f"d_{day}"] = df[f"d_{day}"].astype(object)
        df.loc[(df["store_id"] == STORE) & (df["item_id"] == item), f"d_{day}"] = value
        return df

    return change


# -------------------------------------------------------------------- passing


def test_clean_fixture_passes(m5_raw_dir: Path):
    rep = report(m5_raw_dir)
    assert rep["status"] == "pass"
    assert rep["summary"]["failed"] == 0 and rep["summary"]["blocking_failures"] == []
    names = [c["name"] for c in rep["checks"]]
    assert names[:3] == ["files_present", "required_columns", "store_present"]
    assert all(c["status"] == "pass" for c in rep["checks"])


def test_report_is_written_as_json(m5_raw_dir: Path, tmp_path: Path):
    path = v.write_quality_report(report(m5_raw_dir), tmp_path / "out" / "quality_report.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == v.REPORT_SCHEMA_VERSION
    assert {"name", "status", "blocking", "message", "details"} <= set(saved["checks"][0])


# ------------------------------------------------------- structural failures


ALL_CHECKS = ["files_present", "required_columns", "store_present"] + [
    n for n, _ in v.CONTENT_CHECKS
]


@pytest.mark.parametrize("broken", ["none", "file", "store"])
def test_every_check_is_reported_once(m5_raw_dir: Path, broken: str):
    scope = make_scope(store="XX_9") if broken == "store" else make_scope()
    if broken == "file":
        (m5_raw_dir / "sell_prices.csv").unlink()
    names = [c["name"] for c in report(m5_raw_dir, scope)["checks"]]
    assert names == ALL_CHECKS


def test_missing_file_fails_and_skips_the_rest(m5_raw_dir: Path):
    (m5_raw_dir / "calendar.csv").unlink()
    rep = report(m5_raw_dir)
    assert rep["status"] == "fail"
    first = rep["checks"][0]
    assert first["name"] == "files_present" and first["status"] == "fail"
    assert "calendar.csv" in first["message"]
    assert all(c["status"] == "skipped" for c in rep["checks"][1:])


def test_validation_file_is_not_required(m5_raw_dir: Path):
    (m5_raw_dir / "sales_train_validation.csv").unlink()
    assert report(m5_raw_dir)["status"] == "pass"


def test_missing_column_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "sell_prices.csv", lambda df: df.drop(columns=["sell_price"]))
    res = results(m5_raw_dir)
    assert res["required_columns"].status == "fail"
    assert "sell_price" in res["required_columns"].message
    assert res["units_sold_valid"].status == "skipped"


def test_unknown_store_fails(m5_raw_dir: Path):
    res = results(m5_raw_dir, make_scope(store="XX_9"))
    assert res["store_present"].status == "fail"
    assert "XX_9" in res["store_present"].message


def test_unknown_sales_file_is_a_scope_error(m5_raw_dir: Path):
    scope = make_scope()
    object.__setattr__(scope, "sales_file", "other.csv")
    with pytest.raises(v.ScopeError, match="sales_file"):
        v.run_checks(m5_raw_dir, scope)


# ---------------------------------------------------------- content failures


def test_calendar_gap_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "calendar.csv", lambda df: df.drop(index=10))
    res = results(m5_raw_dir)["calendar_dates"]
    assert res.status == "fail" and res.blocking
    assert res.details["missing_dates"] == ["2011-02-08"]


def test_data_shorter_than_split_fails(m5_raw_dir: Path):
    res = results(m5_raw_dir, make_scope(last_day=N_DAYS + 28))["sales_days"]
    assert res.status == "fail"
    assert "split needs" in res.message


def test_duplicate_item_row_fails(m5_raw_dir: Path):
    rewrite(m5_raw_dir / SALES, lambda df: pd.concat([df, df.iloc[[0]]]))
    res = results(m5_raw_dir)["sales_ids"]
    assert res.status == "fail"
    assert res.details["duplicate_item_ids"] == ["FOODS_1_001"]


def test_null_id_fails(m5_raw_dir: Path):
    def change(df):
        df.loc[(df["store_id"] == STORE) & (df["item_id"] == "FOODS_1_002"), "dept_id"] = None
        return df

    rewrite(m5_raw_dir / SALES, change)
    res = results(m5_raw_dir)["sales_ids"]
    assert res.status == "fail" and res.details["null_id_values"] == {"dept_id": 1}


@pytest.mark.parametrize(
    ("value", "field"),
    [(-1, "negative"), (1.5, "non_integer"), (None, "null_or_non_numeric")],
)
def test_bad_units_fail(m5_raw_dir: Path, value, field: str):
    rewrite(m5_raw_dir / SALES, set_units(5, value))
    res = results(m5_raw_dir)["units_sold_valid"]
    assert res.status == "fail" and res.blocking
    assert res.details[field] == 1


def test_bad_units_in_other_store_are_ignored(m5_raw_dir: Path):
    def change(df):
        df.loc[df["store_id"] == "TX_1", "d_5"] = -3
        return df

    rewrite(m5_raw_dir / SALES, change)
    assert results(m5_raw_dir)["units_sold_valid"].status == "pass"


def test_zero_price_fails(m5_raw_dir: Path):
    def change(df):
        df.loc[(df["store_id"] == STORE) & (df.index % 50 == 0), "sell_price"] = 0
        return df

    rewrite(m5_raw_dir / "sell_prices.csv", change)
    res = results(m5_raw_dir)["sell_price_valid"]
    assert res.status == "fail" and res.details["non_positive_prices"] > 0


def test_duplicate_price_key_fails(m5_raw_dir: Path):
    def change(df):
        first = df[df["store_id"] == STORE].iloc[[0]]
        return pd.concat([df, first])

    rewrite(m5_raw_dir / "sell_prices.csv", change)
    assert results(m5_raw_dir)["sell_price_valid"].details["duplicate_keys"] == 1


def test_missing_scope_item_fails(m5_raw_dir: Path):
    res = results(m5_raw_dir, make_scope(items=ITEMS + ["FOODS_9_999"]))["scope_items_present"]
    assert res.status == "fail"
    assert res.details["missing"] == ["FOODS_9_999"]


# --------------------------------------------------------------- warnings


def test_price_gap_after_availability_is_a_warning(m5_raw_dir: Path):
    rep = report(m5_raw_dir, make_scope(items=ITEMS + ["HOBBIES_1_004"]))
    check = next(c for c in rep["checks"] if c["name"] == "scope_item_prices")
    assert check["status"] == "warn" and not check["blocking"]
    assert check["details"]["per_item"]["HOBBIES_1_004"]["gaps_after_first_price"] > 0
    assert rep["status"] == "pass"  # warnings do not block


def test_prices_before_availability_are_expected(m5_raw_dir: Path):
    def change(df):
        late = (df["item_id"] == "HOBBIES_1_003") & (df["wm_yr_wk"] < 11101 + 17)
        return df[~late]

    rewrite(m5_raw_dir / "sell_prices.csv", change)
    res = results(m5_raw_dir, make_scope(items=ITEMS + ["HOBBIES_1_003"]))["scope_item_prices"]
    assert res.status == "pass"
    assert res.details["per_item"]["HOBBIES_1_003"]["weeks_before_first_price"] == 17


def test_item_without_any_price_is_a_warning(m5_raw_dir: Path):
    rewrite(m5_raw_dir / "sell_prices.csv", lambda df: df[df["item_id"] != "FOODS_1_001"])
    res = results(m5_raw_dir)["scope_item_prices"]
    assert res.status == "warn"
    assert res.details["per_item"]["FOODS_1_001"]["gaps_after_first_price"] is None


def test_store_zero_sales_day_is_a_warning(m5_raw_dir: Path):
    def change(df):
        df.loc[df["store_id"] == STORE, "d_10"] = 0
        return df

    rewrite(m5_raw_dir / SALES, change)
    rep = report(m5_raw_dir)
    check = next(c for c in rep["checks"] if c["name"] == "store_zero_sales_days")
    assert check["status"] == "warn" and check["details"]["dates"] == ["2011-02-07"]
    assert rep["status"] == "pass"


def test_crashing_check_is_reported_not_hidden(m5_raw_dir: Path, monkeypatch):
    def boom(raw, scope):
        raise RuntimeError("unexpected")

    checks = [(n, boom if n == "sales_ids" else c) for n, c in v.CONTENT_CHECKS]
    monkeypatch.setattr(v, "CONTENT_CHECKS", checks)
    rep = report(m5_raw_dir)
    check = next(c for c in rep["checks"] if c["name"] == "sales_ids")
    assert check["status"] == "fail" and "RuntimeError" in check["message"]
    assert rep["status"] == "fail"


# ---------------------------------------------------------------------- CLI


def test_main_exit_codes(m5_raw_dir: Path, tmp_path: Path):
    scope_path = tmp_path / "scope.json"
    scope = make_scope()
    raw_scope = {
        "schema_version": "1.0.0",
        "store_id": scope.store_id,
        "sales_file": scope.sales_file,
        "horizon_days": 28,
        "split": {
            p: {"first_day": r.first_day, "last_day": r.last_day} for p, r in scope.split.items()
        },
        "items": [{"item_id": i, "demand_group": "high"} for i in scope.item_ids],
    }
    scope_path.write_text(json.dumps(raw_scope), encoding="utf-8")
    out = tmp_path / "quality_report.json"
    args = ["--raw-dir", str(m5_raw_dir), "--scope", str(scope_path), "--out", str(out)]

    assert v.main(args) == 0 and out.is_file()
    (m5_raw_dir / "calendar.csv").unlink()
    assert v.main(args) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "fail"


def test_main_bad_scope_returns_error(tmp_path: Path):
    assert v.main(["--scope", str(tmp_path / "missing.json")]) == 1
