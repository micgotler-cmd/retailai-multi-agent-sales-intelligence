"""Data Quality page (P-13 step 3) and its table helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app import tables
from tests.app.test_streamlit_app import start, text

PAGE = "pages/data_quality.py"


def read(run_dir: Path, name: str) -> dict:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------ with real tools


def test_page_shows_all_four_sections(tool_run):
    at = start(PAGE)
    assert [h.value for h in at.header] == [
        "1. Validation of the raw M5 files",
        "2. Cleaning (rules T-13)",
        "3. Fields and missing values (dataset contract)",
        "4. Gate 1: clean data against the contract",
    ]
    assert not at.warning  # nothing missing


def test_validation_section_matches_the_report(tool_run):
    quality = read(tool_run, "quality_report.json")
    at = start(PAGE)
    checks = at.dataframe[0].value
    assert list(checks["Check"]) == [c["name"] for c in quality["checks"]]
    assert list(checks.columns) == ["Check", "Status", "Blocking", "Result"]
    assert f"Validation status: **{quality['status']}**" in text(at)
    assert str(quality["summary"]["checks"]) in [m.value for m in at.metric]


def test_cleaning_section_matches_the_log(tool_run):
    log = read(tool_run, "cleaning_log.json")
    at = start(PAGE)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Rows in"] == f"{log['rows_in']:,}"
    assert metrics["Rows out"] == f"{log['rows_out']:,}"
    actions = at.dataframe[1].value
    assert len(actions) == 3
    dropped = log["actions"][0]["rows_dropped"]
    assert f"{dropped:,} rows dropped" in actions["Result"].iloc[0]
    per_item = at.dataframe[2].value
    assert per_item["Rows dropped"].sum() == dropped


def test_fields_and_gate1_match_the_contract(tool_run):
    contract = read(tool_run, "dataset_contract.json")
    check = read(tool_run, "contract_check.json")
    at = start(PAGE)
    fields = at.dataframe[3].value
    assert list(fields["Field"]) == [f["name"] for f in contract["fields"]]
    price = fields[fields["Field"] == "sell_price"].iloc[0]
    assert price["Missing values"].startswith("Never imputed")
    gate = at.dataframe[4].value
    assert list(gate["Check"]) == [c["name"] for c in check["checks"]]
    assert "Blocking" not in gate.columns  # the contract check has no blocking flag
    assert f"Contract check: **{check['status']}**" in text(at)


def test_no_data_rows_are_shown(tool_run):
    """T-04: the page shows reports only; no value of a units_sold column appears."""
    at = start(PAGE)
    columns = {c for df in at.dataframe for c in df.value.columns}
    assert not columns & {"units_sold", "sell_price", "date", "snap"}


# ----------------------------------------------------------------- failures


def test_failed_contract_is_shown_as_an_error(tool_run):
    check = read(tool_run, "contract_check.json")
    check["status"] = "fail"
    check["failed_rules"] = ["unique_keys"]
    check["checks"][5]["status"] = "fail"
    (tool_run / "contract_check.json").write_text(json.dumps(check), encoding="utf-8")
    at = start(PAGE)
    errors = [e.body for e in at.error]
    assert any("Contract check: **fail**" in e for e in errors)
    assert "Failed rules: unique_keys" in errors


def test_missing_and_broken_files_give_messages(tool_run):
    (tool_run / "cleaning_log.json").unlink()
    (tool_run / "dataset_contract.json").write_text("{broken", encoding="utf-8")
    at = start(PAGE)
    warnings = " ".join(w.value for w in at.warning)
    assert "no cleaning_log.json" in warnings
    assert "dataset_contract.json not valid JSON" in warnings
    headers = [h.value for h in at.header]
    assert "1. Validation of the raw M5 files" in headers  # the rest still shows


# ------------------------------------------------------------- table helpers


def test_helpers_accept_partial_reports():
    assert tables.check_rows({}) == []
    assert tables.action_rows({"actions": [{"action": "new_rule"}]}) == [
        {"Action": "new_rule", "Result": "", "Rule": ""}
    ]
    assert tables.first_sale_rows({}) == []
    assert tables.field_rows({"fields": [{"name": "x", "nullable": True}]})[0][
        "Missing values"
    ] == ("Allowed")


def test_long_value_lists_are_shortened():
    field = {"name": "item_id", "type": "string", "allowed_values": [f"I{i}" for i in range(20)]}
    rule = tables.field_rows({"fields": [field]})[0]["Allowed values / range"]
    assert rule == "one of: I0, I1, I2, I3, I4, I5 (+14 more)"


def test_missing_counts_show_a_question_mark():
    rows = tables.action_rows({"actions": [{"action": "drop_rows_before_first_sale"}]})
    assert rows[0]["Result"] == "? rows dropped"
