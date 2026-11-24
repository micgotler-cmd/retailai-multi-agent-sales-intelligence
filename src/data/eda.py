"""Exploratory data analysis for Crew 1 (Agent 3, Business Analyst logic, P-05).

Reads `clean_data.csv` and computes every statistic and chart deterministically
in Python, on the **training period only** (d_1 to d_1885, T-09), so the test
period never influences feature or modeling decisions.

Outputs (written to a git-ignored folder):
- `eda_summary.json`: numbered facts (F01, F02, ...) with value, unit,
  definition and period, plus the tables behind the charts. This is the only
  evidence Agent 3 may use; it must cite fact ids and never invent numbers.
- `eda_report.html`: one self-contained page with charts and aggregate tables
  (no raw data rows, T-04).
- `insights.md`: a first, template-based version of the findings, each
  sentence citing its fact ids. Agent 3 may rewrite it in P-04 from the same facts.

Comparisons between categories and demand groups use normalized metrics
(average daily units per item, computed per item-day), not only totals.
SNAP, event and price findings are descriptive associations, not causal effects.
Closure days (store_closed = 1) are excluded from pattern averages.

Usage (from the repository root), after the cleaning step:
    uv run python -m src.data.eda
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display; deterministic file output

import matplotlib.pyplot as plt
import pandas as pd

from src.data.scope import DEFAULT_SCOPE_PATH, DataScope, ScopeError, load_scope
from src.utils.logging_setup import setup_from_env

logger = logging.getLogger(__name__)
logging.getLogger("matplotlib").setLevel(logging.WARNING)  # quiet font/category notices

COUNT_UNITS = {"items", "item-days", "units", "days", "changes"}

SUMMARY_SCHEMA_VERSION = "1.0.0"
REQUIRED_COLUMNS = [
    "date",
    "item_id",
    "dept_id",
    "cat_id",
    "units_sold",
    "sell_price",
    "wm_yr_wk",
    "event_name_1",
    "event_type_1",
    "snap",
    "store_closed",
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
GROUP_ORDER = ["high", "medium", "low"]
ASSOCIATION_NOTE = (
    "Descriptive association only: differences are not causal effects. Other factors "
    "(season, day of week, product mix) are not controlled for."
)
AVG_DEF = "Average daily units per item: total units / number of item-days"


class EDAError(Exception):
    """Raised when the clean data cannot be analysed."""


# --------------------------------------------------------------------- facts


@dataclass
class Fact:
    """One traceable statistic."""

    id: str
    topic: str
    metric: str
    value: float | int | str
    unit: str
    definition: str
    keys: dict = field(default_factory=dict)


class FactBook:
    """Collects facts with stable ids (F01, F02, ...) in the order they are added."""

    def __init__(self) -> None:
        self.facts: list[Fact] = []

    def add(self, topic: str, metric: str, value, unit: str, definition: str, **keys) -> str:
        """Add a fact and return its id. Floats are rounded to 4 decimals."""
        if isinstance(value, float):
            value = round(value, 4)
        fact_id = f"F{len(self.facts) + 1:02d}"
        self.facts.append(Fact(fact_id, topic, metric, value, unit, definition, keys))
        return fact_id

    def get(self, fact_id: str) -> Fact:
        """The fact with this id."""
        return next(f for f in self.facts if f.id == fact_id)


def fmt(value, unit: str = "") -> str:
    """Display format used everywhere (report and insights), so numbers can be traced."""
    if isinstance(value, str):
        return value
    if unit == "%":
        return f"{value:.1f}%"
    if isinstance(value, int) or unit in COUNT_UNITS:
        return f"{round(value):,}" if float(value).is_integer() else f"{value:.1f}"
    return f"{value:.2f}"


# --------------------------------------------------------------- preparation


def load_clean(path: Path) -> pd.DataFrame:
    """Read clean_data.csv and check the columns EDA needs."""
    if not path.is_file():
        raise EDAError(f"Clean data not found: {path}. Run `uv run python -m src.data.cleaning`.")
    df = pd.read_csv(path, parse_dates=["date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise EDAError(f"clean_data.csv is missing column(s): {', '.join(missing)}")
    return df


def train_last_date(df: pd.DataFrame, scope: DataScope) -> pd.Timestamp:
    """Date of the last training day, d_<train.last_day>.

    The clean data ends on d_<scope.last_day> (contract guarantee), so the
    training end is that date minus the validation and test days.
    """
    if df.empty:
        raise EDAError("Clean data is empty")
    offset = scope.last_day - scope.split["train"].last_day
    return df["date"].max() - pd.Timedelta(days=offset)


def training_rows(df: pd.DataFrame, scope: DataScope) -> pd.DataFrame:
    """Rows on or before the last training day, with the demand group added."""
    train = df[df["date"] <= train_last_date(df, scope)].copy()
    if train.empty:
        raise EDAError("No rows in the training period")
    unknown = sorted(set(train["item_id"]) - set(scope.items))
    if unknown:
        raise EDAError(f"Item(s) not in the approved scope: {', '.join(unknown)}")
    train["demand_group"] = train["item_id"].map(scope.items)
    return train


def avg_per_item_day(df: pd.DataFrame, by: str | list[str]) -> pd.Series:
    """Mean units per item-day for each group (each row is one item-day)."""
    return df.groupby(by, observed=True)["units_sold"].mean()


def pct_diff(a: float, b: float) -> float:
    """Percentage difference of a relative to b."""
    return (a / b - 1) * 100 if b else float("nan")


# ------------------------------------------------------------------ analyses


def overview(train: pd.DataFrame, book: FactBook, last: pd.Timestamp) -> dict:
    """Size of the analysed data."""
    closed_days = train.loc[train["store_closed"] == 1, "date"].nunique()
    ids = {
        "items": book.add(
            "overview",
            "items",
            int(train["item_id"].nunique()),
            "items",
            "Products analysed (T-03)",
        ),
        "first_date": book.add(
            "overview",
            "first_date",
            str(train["date"].min().date()),
            "date",
            "First date in the training period",
        ),
        "last_date": book.add(
            "overview",
            "train_last_date",
            str(last.date()),
            "date",
            "Last training date (d_1885, T-09)",
        ),
        "item_days": book.add(
            "overview",
            "item_days",
            len(train),
            "item-days",
            "Rows analysed (one per item per day, from each item's first sale)",
        ),
        "total_units": book.add(
            "overview",
            "total_units",
            int(train["units_sold"].sum()),
            "units",
            "Total units sold in the training period",
        ),
        "avg": book.add(
            "overview",
            "avg_daily_units_per_item",
            float(train["units_sold"].mean()),
            "units/item/day",
            AVG_DEF,
        ),
        "closed": book.add(
            "overview",
            "store_closed_days",
            int(closed_days),
            "days",
            "Closure days (25 December) excluded from pattern averages",
        ),
    }
    return ids


def segment_table(open_days: pd.DataFrame, by: str) -> pd.DataFrame:
    """Normalized and total metrics per segment (category or demand group)."""
    g = open_days.groupby(by, observed=True)
    table = pd.DataFrame(
        {
            "items": g["item_id"].nunique(),
            "item_days": g.size(),
            "total_units": g["units_sold"].sum(),
            "avg_daily_units_per_item": g["units_sold"].mean(),
            "zero_sales_share_pct": g["units_sold"].apply(lambda s: (s == 0).mean() * 100),
        }
    )
    table["share_of_total_units_pct"] = table["total_units"] / table["total_units"].sum() * 100
    return table


def segment_facts(table: pd.DataFrame, by: str, book: FactBook) -> dict:
    """Facts per segment: item count, normalized average, zero share, share of units."""
    ids = {}
    for name, row in table.iterrows():
        ids[name] = {
            "items": book.add(
                by, "items", int(row["items"]), "items", "Products in the segment", **{by: name}
            ),
            "avg": book.add(
                by,
                "avg_daily_units_per_item",
                float(row["avg_daily_units_per_item"]),
                "units/item/day",
                AVG_DEF + " (open days)",
                **{by: name},
            ),
            "zero": book.add(
                by,
                "zero_sales_share",
                float(row["zero_sales_share_pct"]),
                "%",
                "Share of item-days with zero units (open days)",
                **{by: name},
            ),
            "share": book.add(
                by,
                "share_of_total_units",
                float(row["share_of_total_units_pct"]),
                "%",
                "Share of all units sold (totals, not normalized)",
                **{by: name},
            ),
        }
    return ids


def item_table(train: pd.DataFrame, open_days: pd.DataFrame) -> pd.DataFrame:
    """Per-item statistics, including a first-year vs last-year trend."""
    rows = []
    for item, df in open_days.groupby("item_id"):
        df = df.sort_values("date")
        first_year = df[df["date"] < df["date"].min() + pd.Timedelta(days=365)]
        last_year = df[df["date"] > df["date"].max() - pd.Timedelta(days=365)]
        rows.append(
            {
                "item_id": item,
                "dept_id": df["dept_id"].iloc[0],
                "demand_group": df["demand_group"].iloc[0],
                "first_sale": str(train.loc[train["item_id"] == item, "date"].min().date()),
                "days": len(df),
                "avg_daily_units": df["units_sold"].mean(),
                "zero_sales_share_pct": (df["units_sold"] == 0).mean() * 100,
                "trend_pct": pct_diff(
                    last_year["units_sold"].mean(), first_year["units_sold"].mean()
                ),
            }
        )
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    table = pd.DataFrame(rows)
    table["_g"] = table["demand_group"].map(order)
    return table.sort_values(["_g", "avg_daily_units"], ascending=[True, False]).drop(columns="_g")


def item_facts(items: pd.DataFrame, book: FactBook) -> dict:
    """Store-level facts derived from the item table."""
    top = items.loc[items["avg_daily_units"].idxmax()]
    sparse = items.loc[items["zero_sales_share_pct"].idxmax()]
    return {
        "top_item": book.add(
            "items",
            "highest_avg_item",
            str(top["item_id"]),
            "item",
            "Item with the highest average daily units",
        ),
        "top_avg": book.add(
            "items",
            "highest_avg_daily_units",
            float(top["avg_daily_units"]),
            "units/item/day",
            AVG_DEF,
            item_id=top["item_id"],
        ),
        "sparse_item": book.add(
            "items",
            "most_intermittent_item",
            str(sparse["item_id"]),
            "item",
            "Item with the highest share of zero-sales days",
        ),
        "sparse_zero": book.add(
            "items",
            "highest_zero_sales_share",
            float(sparse["zero_sales_share_pct"]),
            "%",
            "Share of zero-sales days",
            item_id=sparse["item_id"],
        ),
        "growing": book.add(
            "items",
            "items_growing",
            int((items["trend_pct"] > 0).sum()),
            "items",
            "Items whose last-365-day average is above their first-365-day average",
        ),
        "declining": book.add(
            "items",
            "items_declining",
            int((items["trend_pct"] < 0).sum()),
            "items",
            "Items whose last-365-day average is below the first",
        ),
    }


def calendar_pattern(
    open_days: pd.DataFrame, key: pd.Series, labels: list[str], topic: str, book: FactBook
) -> tuple[pd.Series, dict]:
    """Average per item-day by weekday or month, with peak, trough and their ratio."""
    means = open_days.groupby(key)["units_sold"].mean()
    means.index = [labels[i] for i in means.index]
    peak, trough = means.idxmax(), means.idxmin()
    ids = {
        "peak": book.add(
            topic,
            "peak",
            peak,
            topic,
            f"{topic.capitalize()} with the highest average daily units per item",
        ),
        "peak_avg": book.add(
            topic, "peak_avg", float(means[peak]), "units/item/day", AVG_DEF, **{topic: peak}
        ),
        "trough": book.add(
            topic,
            "trough",
            trough,
            topic,
            f"{topic.capitalize()} with the lowest average daily units per item",
        ),
        "trough_avg": book.add(
            topic, "trough_avg", float(means[trough]), "units/item/day", AVG_DEF, **{topic: trough}
        ),
        "diff": book.add(
            topic,
            "peak_vs_trough",
            pct_diff(means[peak], means[trough]),
            "%",
            "How much higher the peak average is than the trough average",
        ),
    }
    return means, ids


def comparison(
    open_days: pd.DataFrame, flag: pd.Series, topic: str, book: FactBook, by: str | None = None
) -> tuple[pd.DataFrame, dict]:
    """Average per item-day with vs without a flag (overall and optionally per segment)."""
    frame = open_days.assign(_flag=flag.astype(bool))
    groups = [("all", frame)] + (list(frame.groupby(by)) if by else [])
    rows, ids = [], {}
    for name, df in groups:
        on, off = (
            df.loc[df["_flag"], "units_sold"].mean(),
            df.loc[~df["_flag"], "units_sold"].mean(),
        )
        rows.append({"segment": name, "with": on, "without": off, "diff_pct": pct_diff(on, off)})
        keys = {"segment": name}
        ids[name] = {
            "with": book.add(topic, "avg_with", float(on), "units/item/day", AVG_DEF, **keys),
            "without": book.add(
                topic, "avg_without", float(off), "units/item/day", AVG_DEF, **keys
            ),
            "diff": book.add(
                topic,
                "difference",
                pct_diff(on, off),
                "%",
                f"Difference with vs without ({ASSOCIATION_NOTE})",
                **keys,
            ),
        }
    return pd.DataFrame(rows), ids


def event_types(open_days: pd.DataFrame, book: FactBook) -> tuple[pd.DataFrame, dict]:
    """Average per item-day for each event type, compared with days without an event."""
    kind = open_days["event_type_1"].fillna("no event")
    means = open_days.groupby(kind)["units_sold"].mean()
    days = open_days.groupby(kind)["date"].nunique()
    baseline = means.get("no event", float("nan"))
    order = ["no event"] + sorted(t for t in means.index if t != "no event")
    rows, ids = [], {}
    for name in order:
        rows.append(
            {
                "event_type": name,
                "days": int(days[name]),
                "avg_daily_units_per_item": means[name],
                "diff_vs_no_event_pct": pct_diff(means[name], baseline),
            }
        )
        if name == "no event":
            continue
        ids[name] = {
            "days": book.add(
                "event_type",
                "days",
                int(days[name]),
                "days",
                "Open training days with this event type",
                event_type=name,
            ),
            "avg": book.add(
                "event_type",
                "avg_daily_units_per_item",
                float(means[name]),
                "units/item/day",
                AVG_DEF,
                event_type=name,
            ),
            "diff": book.add(
                "event_type",
                "difference_vs_no_event",
                pct_diff(means[name], baseline),
                "%",
                f"Difference vs days without an event ({ASSOCIATION_NOTE})",
                event_type=name,
            ),
        }
    return pd.DataFrame(rows), ids


def price_table(train: pd.DataFrame) -> pd.DataFrame:
    """Weekly price statistics per item: changes, range."""
    weekly = (
        train.groupby(["item_id", "wm_yr_wk"])["sell_price"]
        .first()
        .reset_index()
        .sort_values(["item_id", "wm_yr_wk"])
    )
    rows = []
    for item, df in weekly.groupby("item_id"):
        prices = df["sell_price"].round(2)
        rows.append(
            {
                "item_id": item,
                "weeks": len(prices),
                "price_changes": int((prices.diff().fillna(0) != 0).sum()),
                "min_price": prices.min(),
                "max_price": prices.max(),
                "range_pct": pct_diff(prices.max(), prices.min()),
            }
        )
    return pd.DataFrame(rows)


def price_facts(prices: pd.DataFrame, book: FactBook) -> dict:
    """Store-level price facts (descriptive; price changes are not promotions)."""
    note = "Week-to-week sell_price changes; M5 has no promotion field, so not promotions"
    return {
        "changed": book.add(
            "price",
            "items_with_price_change",
            int((prices["price_changes"] > 0).sum()),
            "items",
            note,
        ),
        "median_changes": book.add(
            "price",
            "median_price_changes_per_item",
            float(prices["price_changes"].median()),
            "changes",
            note,
        ),
        "max_range": book.add(
            "price",
            "largest_price_range",
            float(prices["range_pct"].max()),
            "%",
            "Largest (max / min - 1) weekly price range of an item",
        ),
        "max_range_item": book.add(
            "price",
            "largest_price_range_item",
            str(prices.loc[prices["range_pct"].idxmax(), "item_id"]),
            "item",
            "Item with the largest weekly price range",
        ),
    }


# --------------------------------------------------------------------- charts


def _png(fig) -> str:
    """Encode a figure as base64 PNG without metadata (stable bytes)."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=90, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def build_charts(open_days: pd.DataFrame, tables: dict) -> list[tuple[str, str, str]]:
    """The eight charts as (title, caption, base64 PNG)."""
    charts = []

    daily = open_days.groupby("date")["units_sold"].mean()
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.plot(daily.index, daily.values, color="#9bb7d4", linewidth=0.6, label="daily")
    ax.plot(daily.index, daily.rolling(28).mean().values, color="#1f4e79", label="28-day mean")
    ax.set_ylabel("units per item per day")
    ax.legend(loc="upper left")
    charts.append(
        (
            "Average daily units per item over time",
            (
                "Normalized by the number of items on sale each day (items launch at different "
                "dates). Closure days excluded."
            ),
            _png(fig),
        )
    )

    monthly = open_days.groupby([pd.Grouper(key="date", freq="MS"), "cat_id"])["units_sold"].mean()
    fig, ax = plt.subplots(figsize=(10, 3.2))
    for cat, series in monthly.groupby(level="cat_id"):
        ax.plot(series.index.get_level_values("date"), series.values, label=cat)
    ax.set_ylabel("units per item per day")
    ax.legend(loc="upper left")
    charts.append(
        (
            "Monthly average daily units per item, by category",
            "Normalized per item, so categories with more products are not favored.",
            _png(fig),
        )
    )

    for key, title in (("weekday", "Day-of-week pattern"), ("month", "Month-of-year pattern")):
        series = tables[key]
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.bar(series.index, series.values, color="#1f4e79")
        ax.set_ylabel("units per item per day")
        ax.tick_params(axis="x", rotation=30 if key == "weekday" else 0)
        charts.append((title, "Average daily units per item; closure days excluded.", _png(fig)))

    items = tables["items"]
    colors = items["demand_group"].map({"high": "#1f4e79", "medium": "#5b8dbf", "low": "#a9c4e0"})
    for column, title, label in (
        ("avg_daily_units", "Average daily units per item, by demand group", "units per day"),
        ("zero_sales_share_pct", "Share of zero-sales days per item", "% of days with 0 units"),
    ):
        fig, ax = plt.subplots(figsize=(10, 3.4))
        ax.bar(items["item_id"], items[column], color=colors)
        ax.set_ylabel(label)
        ax.tick_params(axis="x", rotation=90, labelsize=7)
        charts.append(
            (title, "Dark: high, mid: medium, light: low demand group (T-03).", _png(fig))
        )

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    snap = tables["snap"]
    x = range(len(snap))
    axes[0].bar([i - 0.2 for i in x], snap["with"], width=0.4, label="SNAP day", color="#1f4e79")
    axes[0].bar(
        [i + 0.2 for i in x], snap["without"], width=0.4, label="other day", color="#a9c4e0"
    )
    axes[0].set_xticks(list(x), snap["segment"])
    axes[0].set_title("SNAP vs other days, by category", fontsize=10)
    axes[0].legend(fontsize=8)
    types = tables["event_types"]
    colors = ["#a9c4e0"] + ["#1f4e79"] * (len(types) - 1)
    axes[1].bar(types["event_type"], types["avg_daily_units_per_item"], color=colors)
    axes[1].set_title("Event days by type vs days without an event", fontsize=10)
    axes[1].tick_params(axis="x", labelsize=8)
    for ax in axes:
        ax.set_ylabel("units per item per day")
    charts.append(("SNAP days and event days", ASSOCIATION_NOTE, _png(fig)))

    weekly = open_days.groupby(["item_id", "wm_yr_wk"])["sell_price"].first().reset_index()
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for item, df in weekly.groupby("item_id"):
        ax.plot(range(len(df)), df["sell_price"] / df["sell_price"].iloc[0], linewidth=0.8)
    ax.set_xlabel("weeks since first sale")
    ax.set_ylabel("price / first price")
    charts.append(
        (
            "Weekly price index per item",
            (
                "Each line is one item's weekly price relative to its first price. Price changes "
                "are not promotions (M5 has no promotion field)."
            ),
            _png(fig),
        )
    )
    return charts


# --------------------------------------------------------------------- report


def _html_table(df: pd.DataFrame, percent_columns: tuple[str, ...] = ()) -> str:
    """Escaped HTML table of an aggregate frame."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for _, row in df.iterrows():
        cells = []
        for col, value in row.items():
            if isinstance(value, float):
                value = fmt(value, "%" if col in percent_columns else "")
            cells.append(f"<td>{html.escape(str(value))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_html(summary: dict, charts: list, tables: dict) -> str:
    """Self-contained HTML report: overview facts, charts and aggregate tables."""
    facts = {f["id"]: f for f in summary["facts"]}
    overview_rows = "".join(
        f"<tr><td>{html.escape(facts[i]['definition'])}</td>"
        f"<td>{html.escape(fmt(facts[i]['value'], facts[i]['unit']))}</td>"
        f"<td>{i}</td></tr>"
        for i in summary["sections"]["overview"].values()
    )
    figures = "".join(
        f"<figure><h3>{html.escape(t)}</h3><img alt='{html.escape(t)}' "
        f"src='data:image/png;base64,{b}'><figcaption>{html.escape(c)}</figcaption></figure>"
        for t, c, b in charts
    )
    pct = ("zero_sales_share_pct", "share_of_total_units_pct", "trend_pct", "diff_pct", "range_pct")
    sections = [
        ("Categories", tables["category"].reset_index()),
        ("Demand groups", tables["demand_group"].reset_index()),
        ("Items (training period)", tables["items"]),
        ("Weekly prices per item", tables["prices"]),
    ]
    table_html = "".join(f"<h2>{html.escape(t)}</h2>{_html_table(df, pct)}" for t, df in sections)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RetailAI EDA report</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:0 auto;padding:16px;color:#1b1b1b;background:#fff}}
table{{border-collapse:collapse;margin:8px 0 24px;font-size:13px;width:100%}}
th,td{{border:1px solid #ccd;padding:4px 6px;text-align:left}} th{{background:#eef2f7}}
img{{max-width:100%}} figure{{margin:0 0 28px}} figcaption{{font-size:13px;color:#555}}
.note{{background:#fff7e0;border:1px solid #e6c97a;padding:8px 12px}}
</style></head><body>
<h1>RetailAI: exploratory data analysis</h1>
<p>Store {html.escape(summary["store_id"])}, {len(tables["items"])} products, training period only
({html.escape(summary["period"]["first_date"])} to {html.escape(summary["period"]["last_date"])},
d_1 to d_{summary["period"]["train_last_day"]}, T-09). The validation and test periods are not used.</p>
<p class="note">{html.escape(ASSOCIATION_NOTE)} Price changes are not promotions.
All numbers are computed deterministically in Python; fact ids refer to eda_summary.json.</p>
<h2>Overview</h2><table><thead><tr><th>Measure</th><th>Value</th><th>Fact</th></tr></thead>
<tbody>{overview_rows}</tbody></table>
<h2>Charts</h2>{figures}{table_html}
</body></html>
"""


def _f(book: FactBook, fact_id: str) -> str:
    """Formatted value plus its citation, for insights.md."""
    fact = book.get(fact_id)
    return f"{fmt(fact.value, fact.unit)} [{fact_id}]"


def render_insights(book: FactBook, ids: dict, store_id: str) -> str:
    """Template-based insights.md: every number cites its fact id."""
    o, g, c = ids["overview"], ids["demand_group"], ids["category"]
    w, m, it, s, e, p = (
        ids["weekday"],
        ids["month"],
        ids["items"],
        ids["snap"],
        ids["events"],
        ids["price"],
    )
    f = lambda i: _f(book, i)
    v = lambda i: book.get(i).value
    lines = [
        "# Business insights (training period)",
        "",
        (
            f"Store {store_id}, {f(o['items'])} products, {v(o['first_date'])} to {v(o['last_date'])} "
            "(training period only, T-09). Every number cites a fact in `eda_summary.json`. "
            "Findings about SNAP, events and prices are descriptive associations, not causal effects."
        ),
        "",
        "## Overall demand",
        "",
        (
            f"- The products sold {f(o['total_units'])} units over {f(o['item_days'])} item-days, "
            f"an average of {f(o['avg'])} units per item per day."
        ),
        (
            f"- The store was closed on {f(o['closed'])} days (25 December); these are excluded "
            "from the pattern averages."
        ),
        "",
        "## Demand groups and categories (normalized per item)",
        "",
    ]
    for name in GROUP_ORDER:
        if name in g:
            lines.append(
                f"- {name.capitalize()} demand (items: {f(g[name]['items'])}): {f(g[name]['avg'])} "
                f"units per item per day, zero-sales days {f(g[name]['zero'])}."
            )
    for name, cid in c.items():
        lines.append(
            f"- {name} (items: {f(cid['items'])}): {f(cid['avg'])} units per item per day; "
            f"{f(cid['share'])} of all units sold."
        )
    lines += [
        "",
        "## Products",
        "",
        f"- Highest average: {v(it['top_item'])} at {f(it['top_avg'])} units per day.",
        (
            f"- Most intermittent: {v(it['sparse_item'])}, with zero sales on {f(it['sparse_zero'])} "
            "of its days."
        ),
        (
            f"- Comparing each item's last 365 days with its first 365 days: {f(it['growing'])} items "
            f"sell more, {f(it['declining'])} sell less."
        ),
        "",
        "## Calendar patterns",
        "",
        (
            f"- Day of week: {v(w['peak'])} is the busiest ({f(w['peak_avg'])} units per item per day) "
            f"and {v(w['trough'])} the quietest ({f(w['trough_avg'])}), a difference of {f(w['diff'])}."
        ),
        (
            f"- Month: {v(m['peak'])} is the highest ({f(m['peak_avg'])}) and {v(m['trough'])} the "
            f"lowest ({f(m['trough_avg'])}), a difference of {f(m['diff'])}."
        ),
        "",
        "## SNAP days and events (associations)",
        "",
        (
            f"- On SNAP days the products sold {f(s['all']['with'])} units per item per day, versus "
            f"{f(s['all']['without'])} on other days ({f(s['all']['diff'])})."
        ),
    ]
    if "FOODS" in s:
        lines.append(
            f"- For FOODS items the SNAP-day difference is {f(s['FOODS']['diff'])} "
            f"({f(s['FOODS']['with'])} vs {f(s['FOODS']['without'])})."
        )
    lines += [
        (
            f"- On event days the average was {f(e['all']['with'])} versus {f(e['all']['without'])} "
            f"on other days ({f(e['all']['diff'])})."
        ),
    ]
    for name, tid in ids["event_types"].items():
        lines.append(
            f"- {name} events (days: {f(tid['days'])}): {f(tid['avg'])} units per item per day, "
            f"{f(tid['diff'])} versus days without an event."
        )
    lines += [
        "",
        "## Prices (descriptive)",
        "",
        (
            f"- {f(p['changed'])} items changed price at least once; the median item changed price "
            f"{f(p['median_changes'])} times."
        ),
        (
            f"- The largest weekly price range was {f(p['max_range'])} ({v(p['max_range_item'])}). "
            "M5 has no promotion field, so price changes are not treated as promotions."
        ),
        "",
        "## Limitations",
        "",
        f"- One store and {f(o['items'])} products; patterns may not generalize.",
        (
            "- Many items have intermittent demand, and there is no stock data: a zero can mean no "
            "demand or no stock."
        ),
        "- Associations above do not control for season, weekday or product mix.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------- runner


@dataclass
class EDAResult:
    """Everything the EDA step produces."""

    summary: dict
    html: str
    insights: str


def run_eda(clean: pd.DataFrame, scope: DataScope) -> EDAResult:
    """Compute facts, tables, charts, report and insights from clean data."""
    last = train_last_date(clean, scope)
    train = training_rows(clean, scope)
    open_days = train[train["store_closed"] == 0]
    book = FactBook()
    ids: dict = {"overview": overview(train, book, last)}

    tables: dict = {
        "category": segment_table(open_days, "cat_id"),
        "demand_group": segment_table(open_days, "demand_group").reindex(
            [g for g in GROUP_ORDER if g in set(open_days["demand_group"])]
        ),
    }
    ids["category"] = segment_facts(tables["category"], "cat_id", book)
    ids["demand_group"] = segment_facts(tables["demand_group"], "demand_group", book)

    tables["items"] = item_table(train, open_days)
    ids["items"] = item_facts(tables["items"], book)

    tables["weekday"], ids["weekday"] = calendar_pattern(
        open_days, open_days["date"].dt.day_of_week, WEEKDAYS, "weekday", book
    )
    tables["month"], ids["month"] = calendar_pattern(
        open_days, open_days["date"].dt.month - 1, MONTHS, "month", book
    )
    tables["snap"], ids["snap"] = comparison(
        open_days, open_days["snap"] == 1, "snap", book, by="cat_id"
    )
    tables["events"], ids["events"] = comparison(
        open_days, open_days["event_name_1"].notna(), "events", book
    )
    tables["event_types"], ids["event_types"] = event_types(open_days, book)
    tables["prices"] = price_table(train)
    ids["price"] = price_facts(tables["prices"], book)

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "store_id": scope.store_id,
        "period": {
            "name": "training",
            "first_date": str(train["date"].min().date()),
            "last_date": str(last.date()),
            "train_last_day": scope.split["train"].last_day,
            "note": "Validation and test periods excluded (T-09)",
        },
        "rules": [
            "Comparisons use average daily units per item (per item-day), not only totals",
            "Closure days (store_closed = 1) are excluded from pattern averages",
            ASSOCIATION_NOTE,
            "Price changes are not promotions (M5 has no promotion field)",
        ],
        "facts": [asdict(f) for f in book.facts],
        "sections": ids,
        "tables": {
            "category": _records(tables["category"].reset_index()),
            "demand_group": _records(tables["demand_group"].reset_index()),
            "items": _records(tables["items"]),
            "weekday": {k: round(float(v), 4) for k, v in tables["weekday"].items()},
            "month": {k: round(float(v), 4) for k, v in tables["month"].items()},
            "snap": _records(tables["snap"]),
            "events": _records(tables["events"]),
            "event_types": _records(tables["event_types"]),
            "prices": _records(tables["prices"]),
        },
    }
    charts = build_charts(open_days, tables)
    return EDAResult(
        summary, render_html(summary, charts, tables), render_insights(book, ids, scope.store_id)
    )


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.round(4).to_json(orient="records"))


def cited_ids(insights: str) -> set[str]:
    """Fact ids cited in an insights text, for traceability checks."""
    return set(re.findall(r"\[(F\d{2,})\]", insights))


def write_outputs(result: EDAResult, out_dir: Path) -> list[Path]:
    """Write eda_summary.json, eda_report.html and insights.md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "eda_summary.json", out_dir / "eda_report.html", out_dir / "insights.md"]
    paths[0].write_text(json.dumps(result.summary, indent=2), encoding="utf-8")
    paths[1].write_text(result.html, encoding="utf-8")
    paths[2].write_text(result.insights, encoding="utf-8")
    return paths


def main(argv: list[str] | None = None) -> int:
    """Run the EDA on clean_data.csv; exit code 1 on a data or scope error."""
    setup_from_env()
    parser = argparse.ArgumentParser(description="EDA on the training period of clean_data.csv.")
    parser.add_argument("--clean", type=Path, default=Path("artifacts/clean/clean_data.csv"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/eda"))
    args = parser.parse_args(argv)
    try:
        result = run_eda(load_clean(args.clean), load_scope(args.scope))
    except (EDAError, ScopeError) as exc:
        logger.error("%s", exc)
        return 1
    for path in write_outputs(result, args.out_dir):
        logger.info("Wrote %s", path)
    logger.info("EDA facts: %d", len(result.summary["facts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
