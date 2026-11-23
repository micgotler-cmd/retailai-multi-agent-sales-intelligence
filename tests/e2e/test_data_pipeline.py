"""End-to-end test of the data foundation: validation -> ETL -> cleaning -> contract.

Runs the real command-line entry points. The synthetic tests always run; the
real-data test runs only when the M5 files are in data/raw/ (they are never in
the repository, T-04), so it is skipped on CI and on clean machines.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data import cleaning, contract
from tests.conftest import ITEMS, write_scope_file

OUTPUTS = [
    "quality_report.json",
    "clean_data.csv",
    "cleaning_log.json",
    "dataset_contract.json",
    "contract_check.json",
]
REAL_RAW = Path("data/raw")
REAL_FILES = ["calendar.csv", "sales_train_evaluation.csv", "sell_prices.csv"]


def run_pipeline(raw_dir: Path, scope: Path, out_dir: Path) -> tuple[int, int | None]:
    """Run cleaning (which validates first) and then the contract; return both exit codes."""
    code = cleaning.main(
        ["--raw-dir", str(raw_dir), "--scope", str(scope), "--out-dir", str(out_dir)]
    )
    if code != 0:
        return code, None
    args = ["--clean-dir", str(out_dir), "--raw-dir", str(raw_dir), "--scope", str(scope)]
    return code, contract.main(args)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------- synthetic data


def test_full_pipeline_on_synthetic_data(m5_raw_dir: Path, tmp_path: Path):
    scope = write_scope_file(tmp_path / "scope.json", ITEMS + ["HOBBIES_1_003"])
    out = tmp_path / "run"
    assert run_pipeline(m5_raw_dir, scope, out) == (0, 0)

    for name in OUTPUTS:
        assert (out / name).is_file(), name
    assert read_json(out / "quality_report.json")["status"] == "pass"
    assert read_json(out / "contract_check.json")["status"] == "pass"

    clean = pd.read_csv(out / "clean_data.csv")
    assert set(clean["item_id"]) == set(ITEMS + ["HOBBIES_1_003"])
    assert clean["sell_price"].notna().all()
    log = read_json(out / "cleaning_log.json")
    assert log["rows_out"] == len(clean)
    loaded = contract.load_contract(out / "dataset_contract.json")
    assert loaded["dataset"]["rows"] == len(clean)


def test_pipeline_is_reproducible(m5_raw_dir: Path, tmp_path: Path):
    """Same inputs give byte-identical outputs (M-20)."""
    scope = write_scope_file(tmp_path / "scope.json")
    first, second = tmp_path / "run1", tmp_path / "run2"
    assert run_pipeline(m5_raw_dir, scope, first) == (0, 0)
    assert run_pipeline(m5_raw_dir, scope, second) == (0, 0)
    for name in OUTPUTS:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_corrupt_input_fails_gracefully(m5_raw_dir: Path, tmp_path: Path):
    """A broken calendar stops the run at validation: clear report, no clean data."""
    cal = pd.read_csv(m5_raw_dir / "calendar.csv")
    cal.drop(index=[30, 31]).to_csv(m5_raw_dir / "calendar.csv", index=False)
    scope = write_scope_file(tmp_path / "scope.json")
    out = tmp_path / "run"

    assert run_pipeline(m5_raw_dir, scope, out) == (1, None)
    report = read_json(out / "quality_report.json")
    assert report["status"] == "fail"
    assert "calendar_dates" in report["summary"]["blocking_failures"]
    assert not (out / "clean_data.csv").exists()
    assert not (out / "dataset_contract.json").exists()


def test_unreadable_file_fails_gracefully(m5_raw_dir: Path, tmp_path: Path):
    """A truncated, header-only sales file is reported, not a crash."""
    sales = m5_raw_dir / "sales_train_evaluation.csv"
    sales.write_text(sales.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    scope = write_scope_file(tmp_path / "scope.json")
    out = tmp_path / "run"
    assert run_pipeline(m5_raw_dir, scope, out) == (1, None)
    assert read_json(out / "quality_report.json")["status"] == "fail"


# ------------------------------------------------------------------ real data


@pytest.mark.skipif(
    not all((REAL_RAW / f).is_file() for f in REAL_FILES),
    reason="M5 files not in data/raw/ (download them from Kaggle, see README)",
)
def test_full_pipeline_on_real_data(tmp_path: Path):
    """The approved 20 items of CA_1 (config/data_scope.json), with the known results."""
    out = tmp_path / "real"
    assert run_pipeline(REAL_RAW, Path("config/data_scope.json"), out) == (0, 0)

    report = read_json(out / "quality_report.json")
    assert report["status"] == "pass"
    warnings = {c["name"] for c in report["checks"] if c["status"] == "warn"}
    assert warnings == {"store_zero_sales_days"}  # the Christmas closures

    log = read_json(out / "cleaning_log.json")
    assert (log["rows_in"], log["rows_out"]) == (38_820, 31_278)
    assert log["actions"][1]["rows_flagged"] == 85
    assert read_json(out / "contract_check.json")["status"] == "pass"
