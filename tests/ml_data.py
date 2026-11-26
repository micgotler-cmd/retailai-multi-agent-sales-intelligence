"""Synthetic clean-data frames for the ML tests. Never real M5 rows (T-04)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tests.conftest import ITEMS, N_DAYS, STORE

DAY_1 = pd.Timestamp("2011-01-29")


def day_date(day: int) -> pd.Timestamp:
    """Date of M5 day number `day` (d_1 is 2011-01-29)."""
    return DAY_1 + pd.Timedelta(days=day - 1)


def make_clean(items: list[str] = ITEMS, n_days: int = N_DAYS, seed: int = 0) -> pd.DataFrame:
    """A gap-free clean-data-shaped frame with deterministic daily units per item."""
    rng = np.random.default_rng(seed)
    frames = []
    for item_id in items:
        frames.append(
            pd.DataFrame(
                {
                    "store_id": STORE,
                    "item_id": item_id,
                    "date": [day_date(d) for d in range(1, n_days + 1)],
                    "units_sold": rng.poisson(3, n_days),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def one_item(values: list[float], first_day: int = 1, item_id: str = "FOODS_1_001"):
    """A single item's rows with the given daily units, starting at `first_day`."""
    return pd.DataFrame(
        {
            "store_id": STORE,
            "item_id": item_id,
            "date": [day_date(first_day + i) for i in range(len(values))],
            "units_sold": values,
        }
    )


def with_ids(clean: pd.DataFrame) -> pd.DataFrame:
    return clean.assign(
        dept_id=clean["item_id"].str[:7], cat_id=clean["item_id"].str[:5], state_id="CA"
    )


def make_calendar(n_days: int = N_DAYS + 28) -> pd.DataFrame:
    days = np.arange(1, n_days + 1)
    return pd.DataFrame(
        {
            "date": [day_date(int(d)) for d in days],
            "d": [f"d_{d}" for d in days],
            "event_type_1": [("Sporting" if d % 50 == 0 else None) for d in days],
            "snap": (days % 10 == 0).astype(int),
            "day": days,
        }
    )
