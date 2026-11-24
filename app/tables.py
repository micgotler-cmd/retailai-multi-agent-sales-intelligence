"""Turn the run's JSON reports into display rows for the pages (no computation).

These functions only select and rename values that the deterministic tools
already wrote; they never calculate statistics. They accept partly missing
fields, so an older or broken report shows what it has instead of failing.
"""

from __future__ import annotations

STATUS_ICON = {"pass": "✅ pass", "warn": "⚠️ warn", "fail": "❌ fail", "skipped": "⏭️ skipped"}
ACTION_TITLES = {
    "drop_rows_before_first_sale": "Drop rows before each item's first sale",
    "flag_store_closed": "Flag store-closure days (25 December)",
    "check_prices": "Check prices (never imputed)",
}
MAX_VALUES_SHOWN = 6


def _n(value) -> str:
    """A count with thousands separators, or '?' if the report does not have it."""
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else "?"


def status_label(status: str | None) -> str:
    return STATUS_ICON.get(str(status), str(status))


def check_rows(report: dict) -> list[dict]:
    """One row per check of quality_report.json or contract_check.json."""
    checks = report.get("checks") or []
    with_blocking = any("blocking" in c for c in checks)  # only the validation report has it
    rows = []
    for c in checks:
        row = {"Check": c.get("name", "?"), "Status": status_label(c.get("status"))}
        if with_blocking:
            row["Blocking"] = "yes" if c.get("blocking") else "no"
        row["Result"] = c.get("message", "")
        rows.append(row)
    return rows


def action_rows(log: dict) -> list[dict]:
    """One row per cleaning action, with the counts the cleaning wrote."""
    rows = []
    for a in log.get("actions") or []:
        name = a.get("action", "?")
        if name == "drop_rows_before_first_sale":
            result = f"{_n(a.get('rows_dropped'))} rows dropped"
        elif name == "flag_store_closed":
            result = (
                f"{_n(a.get('rows_flagged'))} rows flagged on {len(a.get('dates') or [])} "
                f"dates; {_n(a.get('flagged_rows_with_sales'))} of them had sales"
            )
        elif name == "check_prices":
            result = (
                f"{_n(a.get('missing_prices'))} missing prices in {_n(a.get('rows_checked'))} rows"
            )
        else:
            result = ""
        rows.append(
            {"Action": ACTION_TITLES.get(name, name), "Result": result, "Rule": a.get("rule", "")}
        )
    return rows


def first_sale_rows(log: dict) -> list[dict]:
    """Per item: first sale date and rows dropped before it (counts, not data rows)."""
    action = next(
        (a for a in log.get("actions") or [] if a.get("action") == "drop_rows_before_first_sale"),
        {},
    )
    dates = action.get("first_sale_date_per_item") or {}
    dropped = action.get("rows_dropped_per_item") or {}
    return [
        {"Item": item, "First sale": dates.get(item, ""), "Rows dropped": dropped.get(item)}
        for item in sorted(set(dates) | set(dropped))
    ]


def _rule(field: dict) -> str:
    parts = []
    values = field.get("allowed_values")
    if values is not None:
        shown = ", ".join(str(v) for v in values[:MAX_VALUES_SHOWN])
        more = len(values) - MAX_VALUES_SHOWN
        parts.append(f"one of: {shown}" + (f" (+{more} more)" if more > 0 else ""))
    if "min" in field:
        parts.append(f"min {field['min']}")
    if "exclusive_min" in field:
        parts.append(f"greater than {field['exclusive_min']}")
    if "max" in field:
        parts.append(f"max {field['max']}")
    return "; ".join(parts)


def field_rows(contract: dict) -> list[dict]:
    """One row per field of dataset_contract.json, with its missing-value rule."""
    missing = contract.get("missing_value_rules") or {}
    return [
        {
            "Field": f.get("name", "?"),
            "Type": f.get("type", ""),
            "Description": f.get("description", ""),
            "Allowed values / range": _rule(f),
            "Missing values": missing.get(f.get("name"))
            or ("Allowed" if f.get("nullable") else "Not allowed"),
        }
        for f in contract.get("fields") or []
    ]
