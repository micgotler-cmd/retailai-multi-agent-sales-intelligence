"""Charts for the Business Insights page, drawn from eda_summary.json tables.

The tables were computed by src/data/eda.py (training period only); these
functions only draw them, they compute nothing. Colors follow the dataviz
reference palette, validated for color-vision deficiency in light and dark
mode: one hue for single-series bars, blue/orange for the two SNAP series,
blue/red (plus sign and label) for above/below "no event". Every chart has a
hover tooltip, and the page offers the same numbers as a table.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

COLORS = {
    "light": {"series": "#2a78d6", "second": "#eb6834", "negative": "#e34948"},
    "dark": {"series": "#3987e5", "second": "#d95926", "negative": "#e66767"},
}
AVG_TITLE = "Average daily units per item"
BAR = {"cornerRadiusEnd": 4}


def _colors(theme: str | None) -> dict[str, str]:
    return COLORS["dark" if theme == "dark" else "light"]


def _axis(title: str) -> alt.Axis:
    return alt.Axis(title=title, grid=True, gridOpacity=0.25, domain=False, ticks=False)


def segment_bars(rows: list[dict], key: str, label: str, theme: str | None = None) -> alt.Chart:
    """Horizontal bars of the average per item for categories or demand groups."""
    df = pd.DataFrame(rows)
    tooltip = [
        alt.Tooltip(f"{key}:N", title=label),
        alt.Tooltip("avg_daily_units_per_item:Q", title=AVG_TITLE, format=".2f"),
        alt.Tooltip("items:Q", title="Items"),
        alt.Tooltip("share_of_total_units_pct:Q", title="Share of all units (%)", format=".1f"),
    ]
    return (
        alt.Chart(df)
        .mark_bar(size=22, color=_colors(theme)["series"], **BAR)
        .encode(
            y=alt.Y(f"{key}:N", sort=list(df[key]), title=None, axis=alt.Axis(ticks=False)),
            x=alt.X("avg_daily_units_per_item:Q", axis=_axis(AVG_TITLE)),
            tooltip=tooltip,
        )
        .properties(height=max(90, 36 * len(df)))
    )


def calendar_bars(values: dict[str, float], label: str, theme: str | None = None) -> alt.Chart:
    """Vertical bars of the average per item by weekday or month, in calendar order."""
    df = pd.DataFrame({label: list(values), "avg": list(values.values())})
    return (
        alt.Chart(df)
        .mark_bar(size=24, color=_colors(theme)["series"], **BAR)
        .encode(
            x=alt.X(f"{label}:N", sort=list(df[label]), title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("avg:Q", axis=_axis(AVG_TITLE)),
            tooltip=[
                alt.Tooltip(f"{label}:N"),
                alt.Tooltip("avg:Q", title=AVG_TITLE, format=".2f"),
            ],
        )
        .properties(height=260)
    )


def snap_bars(rows: list[dict], theme: str | None = None) -> alt.Chart:
    """Grouped bars: SNAP days vs other days, per segment (two series, with a legend)."""
    colors = _colors(theme)
    long = pd.DataFrame(
        [
            {"segment": r["segment"], "days": days, "avg": r[col], "diff_pct": r["diff_pct"]}
            for r in rows
            for days, col in (("SNAP days", "with"), ("Other days", "without"))
        ]
    )
    return (
        alt.Chart(long)
        .mark_bar(size=16, **BAR)
        .encode(
            x=alt.X(
                "segment:N",
                sort=[r["segment"] for r in rows],
                title=None,
                axis=alt.Axis(labelAngle=0),
            ),
            xOffset=alt.XOffset("days:N", sort=["SNAP days", "Other days"]),
            y=alt.Y("avg:Q", axis=_axis(AVG_TITLE)),
            color=alt.Color(
                "days:N",
                sort=["SNAP days", "Other days"],
                scale=alt.Scale(range=[colors["series"], colors["second"]]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("segment:N", title="Segment"),
                alt.Tooltip("days:N", title="Days"),
                alt.Tooltip("avg:Q", title=AVG_TITLE, format=".2f"),
                alt.Tooltip("diff_pct:Q", title="SNAP vs other days (%)", format=".1f"),
            ],
        )
        .properties(height=280)
    )


def event_bars(rows: list[dict], theme: str | None = None) -> alt.Chart:
    """Diverging bars: each event type vs days without an event (%), signed labels."""
    colors = _colors(theme)
    df = pd.DataFrame([r for r in rows if r.get("event_type") != "no event"])
    df["direction"] = df["diff_vs_no_event_pct"].map(lambda v: "higher" if v >= 0 else "lower")
    df["label"] = df["diff_vs_no_event_pct"].map(lambda v: f"{v:+.1f}%")
    base = alt.Chart(df).encode(
        y=alt.Y(
            "event_type:N", sort=list(df["event_type"]), title=None, axis=alt.Axis(ticks=False)
        ),
        x=alt.X("diff_vs_no_event_pct:Q", axis=_axis("Difference vs days without an event (%)")),
    )
    bars = base.mark_bar(size=20, **BAR).encode(
        color=alt.Color(
            "direction:N",
            scale=alt.Scale(
                domain=["higher", "lower"], range=[colors["series"], colors["negative"]]
            ),
            legend=None,  # the sign and the label carry the direction, not color alone
        ),
        tooltip=[
            alt.Tooltip("event_type:N", title="Event type"),
            alt.Tooltip("days:Q", title="Days"),
            alt.Tooltip("avg_daily_units_per_item:Q", title=AVG_TITLE, format=".2f"),
            alt.Tooltip("diff_vs_no_event_pct:Q", title="Difference (%)", format="+.1f"),
        ],
    )
    above = base.transform_filter("datum.diff_vs_no_event_pct >= 0")
    below = base.transform_filter("datum.diff_vs_no_event_pct < 0")
    labels = above.mark_text(dx=6, align="left").encode(text="label:N") + below.mark_text(
        dx=-6, align="right"
    ).encode(text="label:N")
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(opacity=0.5).encode(x="x:Q")
    return (bars + labels + zero).properties(height=max(90, 36 * len(df)))
