"""Tests for the dataset contract and the Gate 1 contract check (synthetic data only)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data import contract as ct
from src.data.cleaning import CLEAN_COLUMNS, clean
from src.data.etl import build_long_table, write_long_table
from tests.conftest import ITEMS, make_scope

SCOPE = make_scope()


@pytest.fixture
def built(m5_raw_dir: Path):
    """Clean data (as read back from CSV) and its contract, from the synthetic raw files."""
    df, log = clean(build_long_table(m5_raw_dir, SCOPE), SCOPE)
    path = write_long_table(df, m5_raw_dir.parent / "clean_data.csv")
    csv = pd.read_csv(path)
    return csv, ct.build_contract(csv, SCOPE, log, m5_raw_dir)


def statuses(df: pd.DataFrame, contract: dict) -> dict[str, str]:
    return {r.name: r.status for r in ct.check_against_contract(df, contract)}


def failed(df: pd.DataFrame, contract: dict) -> set[str]:
    return {name for name, s in statuses(df, contract).items() if s == "fail"}


# ------------------------------------------------------------------ building


def test_contract_has_all_sections(built):
    _, contract = built
    ct.check_contract_structure(contract)
    assert [f["name"] for f in contract["fields"]] == CLEAN_COLUMNS
    assert contract["schema_version"] == ct.CONTRACT_SCHEMA_VERSION


def test_allowed_values_come_from_scope(built):
    _, contract = built
    fields = {f["name"]: f for f in contract["fields"]}
    assert fields["item_id"]["allowed_values"] == sorted(ITEMS)
    assert fields["store_id"]["allowed_values"] == ["CA_1"]
    assert fields["dept_id"]["allowed_values"] == ["FOODS_1", "HOBBIES_1"]
    assert fields["state_id"]["allowed_values"] == ["CA"]
    assert fields["sell_price"]["nullable"] is False


def test_raw_file_fingerprints(built, m5_raw_dir: Path):
    _, contract = built
    files = {f["file"]: f for f in contract["dataset"]["raw_files"]}
    assert set(files) == {"calendar.csv", "sales_train_evaluation.csv", "sell_prices.csv"}
    cal = files["calendar.csv"]
    assert cal["bytes"] == (m5_raw_dir / "calendar.csv").stat().st_size
    assert len(cal["sha256"]) == 64


def test_fingerprint_changes_with_content(tmp_path: Path):
    path = tmp_path / "f.csv"
    path.write_text("a\n1\n", encoding="utf-8")
    first = ct.file_fingerprint(path)["sha256"]
    path.write_text("a\n2\n", encoding="utf-8")
    assert ct.file_fingerprint(path)["sha256"] != first


def test_contract_round_trip(built, tmp_path: Path):
    _, contract = built
    path = ct.write_json(contract, tmp_path / "dataset_contract.json")
    assert ct.load_contract(path) == contract


# ------------------------------------------------------------------ passing


def test_clean_data_passes_its_contract(built):
    df, contract = built
    results = ct.check_against_contract(df, contract)
    assert [r.name for r in results] == contract["validation_rules"]
    assert all(r.status == "pass" for r in results)
    assert ct.contract_report(results)["status"] == "pass"


# ------------------------------------------------------------------ failures


def test_extra_column_fails(built):
    df, contract = built
    df["promo"] = 0
    assert statuses(df, contract) == {"columns_match": "fail"}  # stops early


def test_missing_column_fails(built):
    df, contract = built
    assert failed(df.drop(columns=["snap"]), contract) == {"columns_match"}


def test_wrong_type_fails(built):
    df, contract = built
    df["units_sold"] = df["units_sold"].astype(object)
    df.loc[3, "units_sold"] = "many"
    assert "field_types" in failed(df, contract)


def test_fractional_integer_fails(built):
    df, contract = built
    df["units_sold"] = df["units_sold"].astype(float)
    df.loc[3, "units_sold"] = 1.5
    assert "field_types" in failed(df, contract)


def test_bad_date_format_fails(built):
    df, contract = built
    df.loc[0, "date"] = "29/01/2011"
    assert "field_types" in failed(df, contract)


def test_missing_required_value_fails(built):
    df, contract = built
    df.loc[5, "sell_price"] = np.nan
    assert "no_unexpected_nulls" in failed(df, contract)


def test_missing_event_is_allowed(built):
    df, contract = built
    assert df["event_name_1"].isna().any()
    assert "no_unexpected_nulls" not in failed(df, contract)


@pytest.mark.parametrize(
    ("column", "value"),
    [("item_id", "FOODS_9_999"), ("store_id", "TX_1"), ("snap", 2), ("store_closed", -1)],
)
def test_unexpected_value_fails(built, column: str, value):
    df, contract = built
    df[column] = df[column].astype(object)
    df.loc[7, column] = value
    assert "allowed_values" in failed(df, contract)


@pytest.mark.parametrize(("column", "value"), [("units_sold", -1), ("sell_price", 0.0)])
def test_out_of_range_fails(built, column: str, value):
    df, contract = built
    df.loc[9, column] = value
    assert "value_ranges" in failed(df, contract)


def test_duplicate_key_fails(built):
    df, contract = built
    df = pd.concat([df.iloc[:10], df.iloc[[5]], df.iloc[10:]], ignore_index=True)
    assert "unique_keys" in failed(df, contract)


def test_date_gap_fails(built):
    df, contract = built
    assert "dates_continuous_per_item" in failed(df.drop(index=20), contract)


def test_date_after_split_fails(built):
    df, contract = built
    last = df.iloc[[-1]].copy()
    last["date"] = "2011-08-17"
    df = pd.concat([df, last], ignore_index=True)
    bad = failed(df, contract)
    assert {"no_future_dates", "value_ranges"} <= bad


def test_unsorted_rows_fail(built):
    df, contract = built
    assert "sorted_by_item_and_date" in failed(df.iloc[::-1].reset_index(drop=True), contract)


# ------------------------------------------------------ contract file problems


def test_contract_missing_section_fails(built):
    _, contract = built
    broken = copy.deepcopy(contract)
    del broken["fields"]
    with pytest.raises(ct.ContractError, match="fields"):
        ct.check_contract_structure(broken)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda c: c.update(schema_version="2.0.0"), "schema_version"),
        (lambda c: c["fields"][0].update(type="datetime"), "unknown type"),
        (lambda c: c["fields"][0].pop("nullable"), "nullable"),
        (lambda c: c["fields"].append(dict(c["fields"][0])), "more than once"),
    ],
)
def test_malformed_contract_fails(built, change, message: str):
    _, contract = built
    broken = copy.deepcopy(contract)
    change(broken)
    with pytest.raises(ct.ContractError, match=message):
        ct.check_contract_structure(broken)


def test_load_contract_errors(tmp_path: Path):
    with pytest.raises(ct.ContractError, match="not found"):
        ct.load_contract(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ct.ContractError, match="not valid JSON"):
        ct.load_contract(bad)


# ---------------------------------------------------------------------- CLI


def test_main_writes_contract_and_check(m5_raw_dir: Path, tmp_path: Path):
    clean_dir = tmp_path / "clean"
    df, log = clean(build_long_table(m5_raw_dir, SCOPE), SCOPE)
    write_long_table(df, clean_dir / "clean_data.csv")
    (clean_dir / "cleaning_log.json").write_text(json.dumps(log), encoding="utf-8")
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "store_id": SCOPE.store_id,
                "sales_file": SCOPE.sales_file,
                "horizon_days": 28,
                "split": {
                    p: {"first_day": r.first_day, "last_day": r.last_day}
                    for p, r in SCOPE.split.items()
                },
                "items": [{"item_id": i, "demand_group": "high"} for i in SCOPE.item_ids],
            }
        ),
        encoding="utf-8",
    )
    args = ["--clean-dir", str(clean_dir), "--raw-dir", str(m5_raw_dir), "--scope", str(scope_path)]
    assert ct.main(args) == 0
    assert ct.load_contract(clean_dir / "dataset_contract.json")
    check = json.loads((clean_dir / "contract_check.json").read_text(encoding="utf-8"))
    assert check["status"] == "pass"


def test_main_without_clean_data_fails(tmp_path: Path):
    assert ct.main(["--clean-dir", str(tmp_path / "nothing")]) == 1
