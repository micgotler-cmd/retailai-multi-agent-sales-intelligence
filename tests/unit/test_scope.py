"""Tests for loading and checking the data scope file."""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from src.data.scope import DEFAULT_SCOPE_PATH, ScopeError, load_scope, parse_scope

VALID = {
    "schema_version": "1.0.0",
    "store_id": "CA_1",
    "sales_file": "sales_train_evaluation.csv",
    "horizon_days": 28,
    "split": {
        "train": {"first_day": 1, "last_day": 144},
        "validation": {"first_day": 145, "last_day": 172},
        "test": {"first_day": 173, "last_day": 200},
    },
    "items": [
        {"item_id": "A", "demand_group": "high"},
        {"item_id": "B", "demand_group": "low"},
    ],
}


def variant(**changes) -> dict:
    raw = copy.deepcopy(VALID)
    raw.update(changes)
    return raw


def test_repository_scope_matches_approved_decisions():
    """config/data_scope.json holds the T-03 items and the T-09 split."""
    scope = load_scope(DEFAULT_SCOPE_PATH)
    assert scope.store_id == "CA_1"
    assert len(scope.item_ids) == 20
    assert Counter(scope.items.values()) == {"high": 7, "medium": 7, "low": 6}
    assert (scope.split["train"].first_day, scope.split["train"].last_day) == (1, 1885)
    assert (scope.split["validation"].first_day, scope.split["validation"].last_day) == (
        1886,
        1913,
    )
    assert (scope.split["test"].first_day, scope.split["test"].last_day) == (1914, 1941)


def test_valid_scope_parses():
    scope = parse_scope(VALID)
    assert scope.item_ids == ["A", "B"]
    assert scope.last_day == 200
    assert scope.split["test"].n_days == 28


def test_missing_file(tmp_path: Path):
    with pytest.raises(ScopeError, match="not found"):
        load_scope(tmp_path / "nope.json")


def test_invalid_json(tmp_path: Path):
    path = tmp_path / "scope.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ScopeError, match="not valid JSON"):
        load_scope(path)


def test_round_trip_from_file(tmp_path: Path):
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    assert load_scope(path).store_id == "CA_1"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (variant(schema_version="2.0.0"), "schema_version"),
        (variant(store_id="  "), "store_id"),
        (variant(horizon_days=True), "horizon_days"),
        (variant(items=[]), "at least one item"),
        (variant(items=[{"item_id": "A", "demand_group": "high"}] * 2), "Duplicate"),
        (variant(items=[{"item_id": "A", "demand_group": "huge"}]), "demand_group"),
        (variant(items=[{"item_id": "A"}]), "demand_group"),
    ],
)
def test_invalid_fields(raw: dict, message: str):
    with pytest.raises(ScopeError, match=message):
        parse_scope(raw)


def test_missing_field():
    raw = copy.deepcopy(VALID)
    del raw["store_id"]
    with pytest.raises(ScopeError, match="store_id"):
        parse_scope(raw)


def test_overlapping_split():
    raw = copy.deepcopy(VALID)
    raw["split"]["validation"]["first_day"] = 140
    with pytest.raises(ScopeError, match="contiguous"):
        parse_scope(raw)


def test_split_must_match_horizon():
    raw = copy.deepcopy(VALID)
    raw["split"]["test"]["last_day"] = 199
    with pytest.raises(ScopeError, match="horizon_days"):
        parse_scope(raw)


def test_train_must_start_at_day_one():
    raw = copy.deepcopy(VALID)
    raw["split"]["train"]["first_day"] = 2
    with pytest.raises(ScopeError, match="day 1"):
        parse_scope(raw)


def test_missing_split_part():
    raw = copy.deepcopy(VALID)
    del raw["split"]["test"]
    with pytest.raises(ScopeError, match="test"):
        parse_scope(raw)
