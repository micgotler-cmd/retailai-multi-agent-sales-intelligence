"""Dataset contract for `clean_data.csv` (P-06, T-12, M-24).

build_contract() writes `dataset_contract.json`: a versioned JSON description
of the clean data (source, keys, selection, fields, missing-value rules,
quality expectations, assumptions and limitations). check_against_contract()
is the Gate 1 check (and the Feature Engineer's re-check): it compares a clean
table with the contract and returns one result per rule. Plain Python, no
schema framework (T-12).

Allowed values come from the approved scope where possible (store, items,
departments, categories, state), not from the data, so the check is not
circular. Event types and the week range are taken from the clean data.

Usage (from the repository root), after `uv run python -m src.data.cleaning`:
    uv run python -m src.data.contract
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.cleaning import CLEAN_COLUMNS
from src.data.etl import KEYS
from src.data.m5_files import FILES
from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope
from src.data.validation import FAIL, PASS, CheckResult
from src.utils.logging_setup import setup_from_env

logger = logging.getLogger(__name__)

CONTRACT_SCHEMA_VERSION = "1.0.0"
FIELD_TYPES = ("date", "string", "integer", "float")
REQUIRED_SECTIONS = (
    "schema_version",
    "dataset",
    "granularity",
    "selection",
    "fields",
    "missing_value_rules",
    "quality_expectations",
    "validation_rules",
    "assumptions",
    "limitations",
)
SOURCE_URL = "https://www.kaggle.com/competitions/m5-forecasting-accuracy"


class ContractError(Exception):
    """Raised when a contract file is missing or malformed."""


# ------------------------------------------------------------------ building


def file_fingerprint(path: Path) -> dict:
    """Size and SHA-256 of a raw file, identifying the exact data version used."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def _field(name: str, kind: str, nullable: bool = False, description: str = "", **rules) -> dict:
    return {"name": name, "type": kind, "nullable": nullable, "description": description, **rules}


def build_fields(clean: pd.DataFrame, scope: DataScope, first_date: str, last_date: str) -> list:
    """Field definitions in column order. Scope-derived allowed values where possible."""
    depts = sorted({i.rsplit("_", 1)[0] for i in scope.item_ids})
    cats = sorted({d.split("_")[0] for d in depts})
    state = scope.store_id.split("_")[0]
    events = sorted(clean["event_type_1"].dropna().astype(str).unique().tolist())
    fields = [
        _field(
            "date",
            "date",
            description="Calendar date (ISO YYYY-MM-DD)",
            min=first_date,
            max=last_date,
        ),
        _field("store_id", "string", description="Store (T-02)", allowed_values=[scope.store_id]),
        _field(
            "item_id", "string", description="Product (T-03)", allowed_values=sorted(scope.item_ids)
        ),
        _field("dept_id", "string", description="Department", allowed_values=depts),
        _field("cat_id", "string", description="Category", allowed_values=cats),
        _field("state_id", "string", description="State of the store", allowed_values=[state]),
        _field("units_sold", "integer", description="Daily units sold (target)", min=0),
        _field(
            "sell_price", "float", description="Weekly price; never imputed (T-13)", exclusive_min=0
        ),
        _field(
            "wm_yr_wk",
            "integer",
            description="Walmart week key",
            min=int(clean["wm_yr_wk"].min()),
            max=int(clean["wm_yr_wk"].max()),
        ),
        _field("event_name_1", "string", nullable=True, description="Calendar event, if any"),
        _field(
            "event_type_1",
            "string",
            nullable=True,
            description="Event type, if any",
            allowed_values=events,
        ),
        _field(
            "snap",
            "integer",
            description=f"SNAP payment day in {state} (0/1)",
            allowed_values=[0, 1],
        ),
        _field(
            "store_closed",
            "integer",
            description="Store closed, 25 December (0/1, T-13)",
            allowed_values=[0, 1],
        ),
    ]
    if [f["name"] for f in fields] != CLEAN_COLUMNS:
        raise ContractError("Contract fields are out of step with the cleaning columns")
    return fields


def build_contract(
    clean: pd.DataFrame, scope: DataScope, cleaning_log: dict, raw_dir: Path
) -> dict:
    """Assemble the contract for a clean table produced by the cleaning step."""
    files = [FILES["calendar"], scope.sales_file, FILES["sell_prices"]]
    first, last = cleaning_log["first_date"], cleaning_log["last_date"]
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "dataset": {
            "name": "M5 Forecasting - Accuracy (Walmart)",
            "source": SOURCE_URL,
            "terms_check": "T-04 approved 2026-11-18: non-commercial academic use; "
            "no redistribution of the data",
            "raw_files": [file_fingerprint(raw_dir / f) for f in files],
            "clean_file": "clean_data.csv",
            "rows": len(clean),
        },
        "granularity": {
            "keys": KEYS,
            "frequency": "daily",
            "row": "one row per store_id x item_id x date",
            "sort_order": ["item_id", "date"],
            "per_item_range": f"from the item's first sale to {last}, no gaps",
        },
        "selection": {
            "store_id": scope.store_id,
            "items": [{"item_id": i, "demand_group": g} for i, g in scope.items.items()],
            "method": "T-03: eligibility on the training period, three demand groups, "
            "deterministic stratified spread (no random seed)",
            "thresholds": {
                "min_history_days": 365,
                "max_zero_sales_share": 0.8,
                "min_price_coverage": 0.95,
            },
            "split": {
                p: {"first_day": r.first_day, "last_day": r.last_day}
                for p, r in scope.split.items()
            },
        },
        "fields": build_fields(clean, scope, first, last),
        "missing_value_rules": {
            "sell_price": "Never imputed; rows before an item's first sale are dropped, so "
            "no price may be missing (T-13)",
            "event_name_1": "Null when there is no event that day",
            "event_type_1": "Null when there is no event that day",
            "other_fields": "No missing values allowed",
        },
        "quality_expectations": {
            "duplicate_keys": 0,
            "date_gaps_per_item": 0,
            "max_date": last,
            "missing_sell_price": 0,
        },
        "validation_rules": [
            "columns_match",
            "field_types",
            "no_unexpected_nulls",
            "allowed_values",
            "value_ranges",
            "unique_keys",
            "dates_continuous_per_item",
            "no_future_dates",
            "sorted_by_item_and_date",
        ],
        "assumptions": [
            "Zeros before an item's first sale mean 'not yet stocked' and are removed",
            "25 December is a store closure, flagged with store_closed = 1",
            "SNAP days and calendar events are known in advance",
        ],
        "limitations": [
            "M5 has no promotion, coupon or discount field; price changes are not promotions",
            "One store (CA_1) and 20 products; results may not generalize",
            "Many items have intermittent demand (many zero-sales days)",
            "No inventory or stock-out data: a zero can mean no demand or no stock",
        ],
    }


# ------------------------------------------------------------------- loading


def load_contract(path: Path) -> dict:
    """Read a contract file and check its structure (plain Python, T-12)."""
    try:
        contract = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Contract file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Contract is not valid JSON: {path} ({exc})") from exc
    check_contract_structure(contract)
    return contract


def check_contract_structure(contract: dict) -> None:
    """Raise ContractError if a section or field definition is missing or malformed."""
    if not isinstance(contract, dict):
        raise ContractError("Contract must be a JSON object")
    missing = [s for s in REQUIRED_SECTIONS if s not in contract]
    if missing:
        raise ContractError(f"Contract is missing section(s): {', '.join(missing)}")
    version = str(contract["schema_version"])
    if version.split(".")[0] != CONTRACT_SCHEMA_VERSION.split(".")[0]:
        raise ContractError(f"Unsupported contract schema_version {version!r}")
    fields = contract["fields"]
    if not isinstance(fields, list) or not fields:
        raise ContractError("Contract 'fields' must be a non-empty list")
    for f in fields:
        if not isinstance(f, dict) or not {"name", "type", "nullable"} <= set(f):
            raise ContractError(f"Field definition needs name, type and nullable: {f!r}")
        if f["type"] not in FIELD_TYPES:
            raise ContractError(f"Field {f['name']!r} has unknown type {f['type']!r}")
    names = [f["name"] for f in fields]
    if len(names) != len(set(names)):
        raise ContractError("Contract lists a field more than once")


# ------------------------------------------------------------------ checking


def _result(name: str, problems: list[str], ok_message: str, **details) -> CheckResult:
    if problems:
        return CheckResult(name, FAIL, True, "; ".join(problems[:10]), details)
    return CheckResult(name, PASS, True, ok_message, details)


def _typed(series: pd.Series, kind: str) -> tuple[pd.Series, int]:
    """Convert to the contract type; return the values and how many non-null failed."""
    present = series.notna()
    if kind == "string":
        bad = present & ~series.map(lambda v: isinstance(v, str))
        return series, int(bad.sum())
    if kind == "date":
        values = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    else:
        values = pd.to_numeric(series, errors="coerce")
    bad = present & values.isna()
    if kind == "integer":
        whole = values.isna() | np.isclose(values.fillna(0) % 1, 0)
        bad |= present & ~whole
    return values, int(bad.sum())


def check_against_contract(df: pd.DataFrame, contract: dict) -> list[CheckResult]:
    """Gate 1: compare a clean table with the contract, one result per rule."""
    fields = {f["name"]: f for f in contract["fields"]}
    expected = list(fields)
    results = [
        _result(
            "columns_match",
            [f"expected columns {expected}, found {list(df.columns)}"]
            if list(df.columns) != expected
            else [],
            "Columns match the contract",
        )
    ]
    if results[0].status == FAIL:
        return results

    typed, type_problems, null_problems, value_problems, range_problems = {}, [], [], [], []
    for name, spec in fields.items():
        values, bad_type = _typed(df[name], spec["type"])
        typed[name] = values
        if bad_type:
            type_problems.append(f"{name}: {bad_type} value(s) are not {spec['type']}")
        nulls = int(df[name].isna().sum())
        if nulls and not spec["nullable"]:
            null_problems.append(f"{name}: {nulls} missing value(s)")
        present = values.dropna()
        if "allowed_values" in spec:
            allowed = spec["allowed_values"]
            unknown = sorted(set(present.tolist()) - set(allowed), key=str)
            if unknown:
                value_problems.append(f"{name}: unexpected value(s) {unknown[:5]}")
        lo, hi = spec.get("min"), spec.get("max")
        if spec["type"] == "date":
            lo = pd.Timestamp(lo) if lo else None
            hi = pd.Timestamp(hi) if hi else None
        if lo is not None and (present < lo).any():
            range_problems.append(f"{name}: {int((present < lo).sum())} value(s) below {lo}")
        if hi is not None and (present > hi).any():
            range_problems.append(f"{name}: {int((present > hi).sum())} value(s) above {hi}")
        if "exclusive_min" in spec and (present <= spec["exclusive_min"]).any():
            n = int((present <= spec["exclusive_min"]).sum())
            range_problems.append(f"{name}: {n} value(s) not above {spec['exclusive_min']}")

    results += [
        _result("field_types", type_problems, "All values have the contract types"),
        _result("no_unexpected_nulls", null_problems, "Missing values only where allowed"),
        _result("allowed_values", value_problems, "All values are allowed"),
        _result("value_ranges", range_problems, "All values are within range"),
    ]

    keyed = pd.DataFrame({k: typed[k] for k in KEYS})
    dups = int(keyed.duplicated().sum())
    results.append(
        _result("unique_keys", [f"{dups} duplicate key(s)"] if dups else [], "Keys are unique")
    )

    last = pd.Timestamp(contract["quality_expectations"]["max_date"])
    gaps = []
    for item, dates in keyed.dropna().groupby("item_id")["date"]:
        dates = dates.drop_duplicates().sort_values()
        span = (dates.iloc[-1] - dates.iloc[0]).days + 1
        if len(dates) != span or dates.iloc[-1] != last:
            gaps.append(str(item))
    results.append(
        _result(
            "dates_continuous_per_item",
            [f"{len(gaps)} item(s) with gaps or not ending on {last.date()}: {gaps[:5]}"]
            if gaps
            else [],
            f"Every item runs without gaps to {last.date()}",
        )
    )
    future = int((keyed["date"] > last).sum())
    results.append(
        _result(
            "no_future_dates",
            [f"{future} row(s) after {last.date()}"] if future else [],
            "No dates after the split end",
        )
    )
    order = keyed[["item_id", "date"]].reset_index(drop=True)
    is_sorted = order.equals(order.sort_values(["item_id", "date"]).reset_index(drop=True))
    results.append(
        _result(
            "sorted_by_item_and_date",
            [] if is_sorted else ["rows are not sorted"],
            "Rows are sorted by item_id, date",
        )
    )
    return results


def contract_report(results: list[CheckResult]) -> dict:
    """Summary of the Gate 1 contract check; status 'fail' if any rule failed."""
    failed = [r.name for r in results if r.status == FAIL]
    return {
        "status": FAIL if failed else PASS,
        "failed_rules": failed,
        "checks": [{"name": r.name, "status": r.status, "message": r.message} for r in results],
    }


def write_json(data: dict, path: Path) -> Path:
    """Write a JSON file, creating the folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Write the contract for the clean data and check the data against it."""
    setup_from_env()
    parser = argparse.ArgumentParser(description="Write and check the dataset contract.")
    parser.add_argument("--clean-dir", type=Path, default=Path("artifacts/clean"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    args = parser.parse_args(argv)
    data_path = args.clean_dir / "clean_data.csv"
    log_path = args.clean_dir / "cleaning_log.json"
    try:
        scope = load_scope(args.scope)
        clean = pd.read_csv(data_path)
        log = json.loads(log_path.read_text(encoding="utf-8"))
        contract = build_contract(clean, scope, log, args.raw_dir)
    except (ScopeError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        logger.error("Cannot build the contract: %s", exc)
        return 1
    logger.info("Wrote %s", write_json(contract, args.clean_dir / "dataset_contract.json"))
    report = contract_report(check_against_contract(clean, contract))
    for check in report["checks"]:
        logger.info("Contract check %s: %s (%s)", check["name"], check["status"], check["message"])
    write_json(report, args.clean_dir / "contract_check.json")
    logger.info("Contract check status: %s", report["status"])
    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
