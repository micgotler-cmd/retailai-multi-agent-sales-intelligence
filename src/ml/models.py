"""The two model variants, their fixed hyperparameter grids and one prediction path (D-05, D-06).

Each variant is a scikit-learn pipeline: one-hot encoding of the categorical features (the
encoder is fitted on training rows only), standard scaling of the numeric features for Ridge,
then the estimator. One global model per variant covers all items.

`predict_units` is the only place predictions are made. It clips them at zero (units cannot
be negative), so backtests, the test forecast and the future forecast follow the same policy.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.ml import feature_spec as spec

SEED = 42
RIDGE = "ridge"
RANDOM_FOREST = "random_forest"
VARIANTS = (RIDGE, RANDOM_FOREST)  # order also breaks ties between equal scores

RIDGE_GRID = {"alpha": [0.1, 1.0, 10.0, 100.0]}  # 4 candidates
RANDOM_FOREST_GRID = {  # 2 x 2 x 2 = 8 candidates
    "n_estimators": [100, 300],
    "max_depth": [8, 16],
    "min_samples_leaf": [5, 20],
}
GRIDS = {RIDGE: RIDGE_GRID, RANDOM_FOREST: RANDOM_FOREST_GRID}
N_JOBS = -1  # random_state fixes the forest, so the thread count does not change results


class ModelError(Exception):
    """Raised when a model cannot be fitted or produces unusable predictions."""


@dataclass(frozen=True)
class Candidate:
    """One variant with one set of hyperparameters."""

    variant: str
    params: dict = field(default_factory=dict)


def candidates() -> list[Candidate]:
    """Every grid point of every variant, in a fixed order."""
    result = []
    for variant in VARIANTS:
        names = list(GRIDS[variant])
        for values in itertools.product(*(GRIDS[variant][n] for n in names)):
            result.append(Candidate(variant, dict(zip(names, values, strict=True))))
    return result


def make_pipeline(candidate: Candidate) -> Pipeline:
    """An unfitted preprocessing + model pipeline for the candidate."""
    if candidate.variant == RIDGE:
        numeric = StandardScaler()
        estimator = Ridge(**candidate.params)
    elif candidate.variant == RANDOM_FOREST:
        numeric = "passthrough"  # trees do not need scaling
        estimator = RandomForestRegressor(random_state=SEED, n_jobs=N_JOBS, **candidate.params)
    else:
        raise ModelError(f"Unknown model variant {candidate.variant!r}")
    prep = ColumnTransformer(
        [
            ("numeric", numeric, spec.NUMERIC_FEATURES),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                spec.CATEGORICAL_FEATURES,
            ),
        ]
    )
    return Pipeline([("prep", prep), ("model", estimator)])


def fit(candidate: Candidate, rows: pd.DataFrame) -> Pipeline:
    """Fit on complete training rows (see `features.training_rows`)."""
    if rows.empty:
        raise ModelError("No training rows")
    if rows[spec.FEATURE_COLUMNS].isna().any().any() or rows[spec.TARGET_COLUMN].isna().any():
        raise ModelError("Training rows must have complete features and a target")
    pipeline = make_pipeline(candidate)
    return pipeline.fit(rows[spec.FEATURE_COLUMNS], rows[spec.TARGET_COLUMN])


def predict_units(pipeline: Pipeline, rows: pd.DataFrame) -> np.ndarray:
    """Predicted units for feature rows, never below zero."""
    if rows[spec.FEATURE_COLUMNS].isna().any().any():
        raise ModelError("Feature rows to predict have missing values")
    predicted = np.asarray(pipeline.predict(rows[spec.FEATURE_COLUMNS]), dtype=float)
    if not np.isfinite(predicted).all():
        raise ModelError("The model produced non-finite predictions")
    return np.clip(predicted, 0.0, None)
