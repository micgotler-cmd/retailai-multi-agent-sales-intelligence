"""Load and check the approved data scope (`config/data_scope.json`).

The scope holds the store (T-02), the selected items and their demand groups
(T-03) and the chronological split (T-09). It is plain JSON checked by plain
Python (T-12 style); no schema framework.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SCOPE_PATH = Path("config/data_scope.json")
SUPPORTED_MAJOR_VERSION = "1"
DEMAND_GROUPS = ("high", "medium", "low")
SPLIT_PARTS = ("train", "validation", "test")


class ScopeError(Exception):
    """Raised when the scope file is missing or invalid."""


@dataclass(frozen=True)
class DayRange:
    """An inclusive range of M5 day numbers (d_<first>..d_<last>)."""

    first_day: int
    last_day: int

    @property
    def n_days(self) -> int:
        """Number of days in the range."""
        return self.last_day - self.first_day + 1


@dataclass(frozen=True)
class DataScope:
    """The approved store, items and split."""

    schema_version: str
    store_id: str
    sales_file: str
    horizon_days: int
    items: dict[str, str]  # item_id -> demand group
    split: dict[str, DayRange]

    @property
    def item_ids(self) -> list[str]:
        """Selected item ids in file order."""
        return list(self.items)

    @property
    def last_day(self) -> int:
        """Last day covered by the split (end of the test period)."""
        return self.split["test"].last_day


def load_scope(path: Path = DEFAULT_SCOPE_PATH) -> DataScope:
    """Read and check the scope file; raise ScopeError with a readable message."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScopeError(f"Scope file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ScopeError(f"Scope file is not valid JSON: {path} ({exc})") from exc
    if not isinstance(raw, dict):
        raise ScopeError("Scope file must contain a JSON object")
    return parse_scope(raw)


def parse_scope(raw: dict) -> DataScope:
    """Build a DataScope from parsed JSON and check every rule."""
    version = _require(raw, "schema_version", str)
    if version.split(".")[0] != SUPPORTED_MAJOR_VERSION:
        raise ScopeError(f"Unsupported scope schema_version {version!r}")
    scope = DataScope(
        schema_version=version,
        store_id=_require_text(raw, "store_id"),
        sales_file=_require_text(raw, "sales_file"),
        horizon_days=_require(raw, "horizon_days", int),
        items=_parse_items(_require(raw, "items", list)),
        split=_parse_split(_require(raw, "split", dict)),
    )
    _check_split(scope)
    return scope


def _require(raw: dict, key: str, kind: type):
    if key not in raw:
        raise ScopeError(f"Scope is missing {key!r}")
    value = raw[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ScopeError(f"Scope field {key!r} must be of type {kind.__name__}")
    return value


def _require_text(raw: dict, key: str) -> str:
    value = _require(raw, key, str).strip()
    if not value:
        raise ScopeError(f"Scope field {key!r} must not be empty")
    return value


def _parse_items(entries: list) -> dict[str, str]:
    items: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ScopeError("Each item must be an object with item_id and demand_group")
        item_id = _require_text(entry, "item_id")
        group = _require_text(entry, "demand_group")
        if group not in DEMAND_GROUPS:
            raise ScopeError(f"Item {item_id}: demand_group must be one of {DEMAND_GROUPS}")
        if item_id in items:
            raise ScopeError(f"Duplicate item_id in scope: {item_id}")
        items[item_id] = group
    if not items:
        raise ScopeError("Scope must list at least one item")
    return items


def _parse_split(raw: dict) -> dict[str, DayRange]:
    split = {}
    for part in SPLIT_PARTS:
        if part not in raw or not isinstance(raw[part], dict):
            raise ScopeError(f"Split is missing {part!r}")
        first = _require(raw[part], "first_day", int)
        last = _require(raw[part], "last_day", int)
        if first < 1 or last < first:
            raise ScopeError(f"Split {part!r}: need 1 <= first_day <= last_day")
        split[part] = DayRange(first, last)
    return split


def _check_split(scope: DataScope) -> None:
    """Parts must be contiguous and in order; validation and test match the horizon."""
    train, val, test = (scope.split[p] for p in SPLIT_PARTS)
    if train.first_day != 1:
        raise ScopeError("Split 'train' must start at day 1")
    if val.first_day != train.last_day + 1 or test.first_day != val.last_day + 1:
        raise ScopeError("Split parts must be contiguous and in order: train, validation, test")
    for name, part in (("validation", val), ("test", test)):
        if part.n_days != scope.horizon_days:
            raise ScopeError(
                f"Split {name!r} has {part.n_days} days; expected horizon_days={scope.horizon_days}"
            )
