"""Shared fixtures. Test data is synthetic and M5-shaped, never real M5 rows (T-04)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

N_DAYS = 200  # evaluation file length; the validation file has N_DAYS - 28 days
STORE = "CA_1"


def _item_units(rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Synthetic daily units per item, covering the cases the selection must handle."""
    days = np.arange(N_DAYS)
    units = {
        f"FOODS_1_{i:03d}": rng.poisson(lam, N_DAYS)
        for i, lam in enumerate([30, 25, 20, 12, 10, 8, 4, 3, 2.5], start=1)
    }
    units["HOBBIES_1_001"] = np.where(days % 2 == 1, 2, 0)  # exact: mean 1, zero share 0.5
    units["HOBBIES_1_002"] = np.where(days % 20 == 0, 1, 0)  # sparse: zero share 0.95
    units["HOBBIES_1_003"] = np.where(days >= 120, 5, 0)  # first sale late: short history
    units["HOBBIES_1_004"] = rng.poisson(6, N_DAYS)  # prices missing for half the weeks
    units["HOBBIES_1_005"] = np.zeros(N_DAYS, dtype=int)  # never sold
    return units


def write_synthetic_m5(raw_dir: Path, seed: int = 0) -> Path:
    """Write the four M5 CSV files used by the inspection into raw_dir."""
    rng = np.random.default_rng(seed)
    raw_dir.mkdir(parents=True, exist_ok=True)

    dates = pd.date_range("2011-01-29", periods=N_DAYS + 28, freq="D")
    cal = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "wm_yr_wk": 11101 + np.arange(len(dates)) // 7,
            "weekday": dates.day_name(),
            "d": [f"d_{i}" for i in range(1, len(dates) + 1)],
            "snap_CA": 0,
        }
    )
    cal.to_csv(raw_dir / "calendar.csv", index=False)

    units = _item_units(rng)
    rows = []
    for store in (STORE, "TX_1"):
        for item, values in units.items():
            dept = item.rsplit("_", 1)[0]
            ids = {
                "id": f"{item}_{store}_evaluation",
                "item_id": item,
                "dept_id": dept,
                "cat_id": dept.split("_")[0],
                "store_id": store,
                "state_id": store[:2],
            }
            rows.append({**ids, **{f"d_{d + 1}": int(v) for d, v in enumerate(values)}})
    evaluation = pd.DataFrame(rows)
    evaluation.to_csv(raw_dir / "sales_train_evaluation.csv", index=False)
    validation = evaluation.drop(columns=[f"d_{d}" for d in range(N_DAYS - 27, N_DAYS + 1)])
    validation["id"] = validation["id"].str.replace("_evaluation", "_validation")
    validation.to_csv(raw_dir / "sales_train_validation.csv", index=False)

    weeks = sorted(cal["wm_yr_wk"].unique())
    prices = [
        {"store_id": store, "item_id": item, "wm_yr_wk": wk, "sell_price": 1.99}
        for store in (STORE, "TX_1")
        for item in units
        for i, wk in enumerate(weeks)
        if not (item == "HOBBIES_1_004" and i % 2 == 1)
    ]
    pd.DataFrame(prices).to_csv(raw_dir / "sell_prices.csv", index=False)
    return raw_dir


@pytest.fixture
def m5_raw_dir(tmp_path: Path) -> Path:
    """A directory with synthetic M5-shaped raw files."""
    return write_synthetic_m5(tmp_path / "raw")
