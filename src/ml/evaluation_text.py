"""Numbered evaluation facts and the check for Agent 6's narrative (P-09).

The facts come only from `metrics.json`. Each numeric fact carries labels (model, metric,
period, demand group) and the narrative may state a number only as the fact's exact display
value, cited with its id, after naming the fact's own model, metric and period in the same
sentence (the shared checker in `src/data/insights_check.py`, evaluation profile). On top of
the shared rules this profile:

- treats dates and day ids as numbers that need a citation (the dated windows are in the
  deterministic report sections),
- refuses causal explanations anywhere (nothing here tests why a model wins),
- requires a citation in every sentence that compares or ranks (better, best, lower ...),
- refuses claims that another model was selected (selection is computed by Python and the
  agent cannot change it), significance or guarantee claims, and promises about the future.

What a check like this cannot see: a wrong sentence around a correctly cited number. The
numbers in the tables and the technical sections are written by Python, not by the agent.
"""

from __future__ import annotations

import re

from src.data.insights_check import (
    NEGATION,
    SENTENCE_END,
    LabelDimension,
    Profile,
    check_text,
)

BASELINE = "seasonal_naive"
MODEL_NAMES = {
    "seasonal_naive": "Seasonal Naive",
    "ridge": "Ridge",
    "random_forest": "Random Forest",
}
UNIT = "units/item-day"
FACT_TOOL = "get_evaluation_facts"
MIN_CITATIONS_PER_TEXT = 2


def _facts_for(metrics: dict) -> list[tuple]:
    """(topic, metric key, value, unit, labels, definition) in a fixed order."""
    selected = metrics["selected_model"]
    models = [BASELINE, "ridge", "random_forest"]
    rows: list[tuple] = [
        ("setup", "items", metrics["n_items"], "items", {}, "Items forecast"),
        ("setup", "horizon", metrics["horizon_days"], "days", {}, "Forecast horizon in days"),
        (
            "setup",
            "backtest_windows",
            len(metrics["models"]["ridge"]["backtest"]["windows"]),
            "windows",
            {},
            "Rolling-origin backtest windows (comparison and tuning only)",
        ),
    ]
    for model in models:
        mean = metrics["models"][model]["backtest"]["mean_overall"]
        for key in ("mae", "rmse"):
            rows.append(
                (
                    "backtest",
                    f"{model}_{key}",
                    mean[key],
                    UNIT,
                    {"model": model, "metric": key, "period": "backtest"},
                    f"{MODEL_NAMES[model]} {key.upper()}, backtest mean (comparison, tuning only)",
                )
            )
    test = metrics["test"]
    for model, scores in ((selected, test), (BASELINE, test["seasonal_naive"])):
        for key in ("mae", "rmse"):
            rows.append(
                (
                    "test",
                    f"{model}_{key}",
                    scores["overall"][key],
                    UNIT,
                    {"model": model, "metric": key, "period": "test"},
                    f"{MODEL_NAMES[model]} {key.upper()} on the final test window, scored once",
                )
            )
    gain = test["improvement_over_baseline_mae"]
    base = test["seasonal_naive"]["overall"]["mae"]
    labels = {"model": selected, "metric": "mae", "period": "test"}
    rows.append(
        (
            "test",
            "mae_improvement",
            gain,
            UNIT,
            labels,
            f"{MODEL_NAMES[selected]} test MAE improvement over Seasonal Naive (positive is better)",
        )
    )
    rows.append(
        (
            "test",
            "mae_improvement_pct",
            gain / base * 100 if base else 0.0,
            "%",
            labels,
            f"{MODEL_NAMES[selected]} test MAE improvement over Seasonal Naive, in percent",
        )
    )
    for model, scores in ((selected, test), (BASELINE, test["seasonal_naive"])):
        for group, entry in scores["per_demand_group"].items():
            rows.append(
                (
                    "test_group",
                    f"{model}_{group}_mae",
                    entry["mae"],
                    UNIT,
                    {"model": model, "metric": "mae", "period": "test", "group": group},
                    f"{MODEL_NAMES[model]} test MAE for the {group}-demand group",
                )
            )
    return rows


def build_facts(metrics: dict) -> list[dict]:
    """Numbered facts F01, F02, ... from a metrics.json document."""
    return [
        {
            "id": f"F{i:02d}",
            "topic": topic,
            "metric": key,
            "value": value,
            "unit": unit,
            "labels": labels,
            "definition": definition,
        }
        for i, (topic, key, value, unit, labels, definition) in enumerate(_facts_for(metrics), 1)
    ]


def _words(*patterns: str) -> re.Pattern:
    return re.compile("|".join(patterns), re.IGNORECASE)


DIMENSIONS = (
    LabelDimension(
        "model",
        {
            "seasonal_naive": _words(r"\bseasonal[- ]naive\b", r"\bbaseline\b"),
            "ridge": _words(r"\bridge\b"),
            "random_forest": _words(r"\brandom[- ]forest\b", r"\bforest\b"),
        },
    ),
    LabelDimension(
        "metric",
        {
            "mae": _words(r"\bMAE\b", r"\bmean absolute error\b"),
            "rmse": _words(r"\bRMSE\b", r"\broot mean squared? error\b"),
        },
    ),
    LabelDimension(
        "period",
        {
            "backtest": _words(r"\bback-?test\w*\b", r"\brolling[- ]origin\b"),
            "test": _words(r"\btest\b", r"\bhold-?out\b"),
        },
    ),
    LabelDimension(
        "group",
        {
            group: _words(rf"\b{group}[- ]demand\b", rf"\bdemand group[: ]+{group}\b")
            for group in ("high", "medium", "low")
        },
        forbid_when_absent=True,
    ),
)

CAUSAL_WORDS = re.compile(
    r"\b(?:caus(?:e|es|ed|ing|al|ality)|driv(?:e|es|en|ing)|leads? to|led to|results? in"
    r"|resulted in|due to|owing to|because|thanks to|explains?|explained by|attribut\w+"
    r"|reason for|boost(?:s|ed|ing)?|trigger(?:s|ed)?)\b",
    re.IGNORECASE,
)
COMPARES = re.compile(
    r"\b(?:better|worse|best|worst|outperform\w*|beats?|beaten|superior|inferior|improv\w+"
    r"|reduc\w+|lower|higher|more accurate|less accurate|gain\w*)\b",
    re.IGNORECASE,
)
SELECTION = re.compile(
    r"\b(?:selected|chosen|picked|winner|winning|champion|recommended|best model)\b", re.IGNORECASE
)
OVERCLAIMS = re.compile(
    r"\b(?:significant(?:ly)?|statistically|guarantee[sd]?|proves?|proven|certain(?:ly)?"
    r"|definitely|always)\b"
    r"|\bwill\s+(?:outperform|beat|perform|be\s+(?:more\s+)?accurate|achieve|reach)\b",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[\s*F\d{2,}")
HEADING_OR_RULE = re.compile(r"^\s*(?:#|\|)")


def _sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(text) if s.strip() and not HEADING_OR_RULE.match(s)]


def _claim_problems(text: str, selected: str) -> list[str]:
    problems = []
    for sentence in _sentences(text):
        short = " ".join(sentence.split())[:70]
        negated = re.search(NEGATION, sentence, re.IGNORECASE)
        if CAUSAL_WORDS.search(sentence) and not negated:
            problems.append(
                f"Causal or explanatory claim in '{short}': this report does not test why a "
                "model performs as it does; state the measured result only"
            )
        if COMPARES.search(sentence) and not CITATION.search(sentence):
            problems.append(
                f"'{short}' compares or ranks without a cited fact; cite the values it rests on"
            )
        if OVERCLAIMS.search(sentence):
            problems.append(
                f"Unsupported claim in '{short}': no significance test or guarantee exists; "
                "describe the measured result only"
            )
        if SELECTION.search(sentence) and not negated:
            named = {
                model
                for model, name in MODEL_NAMES.items()
                if model != BASELINE
                and re.search(rf"\b{name.split()[0]}\b", sentence, re.IGNORECASE)
            }
            if named and selected not in named:
                problems.append(
                    f"'{short}' says another model was selected; the selection is computed by "
                    f"Python and is {MODEL_NAMES[selected]}"
                )
    return problems


def check_evaluation_text(text: str, metrics: dict) -> list[str]:
    """Problems with one narrative text; [] means it may be saved."""
    facts = build_facts(metrics)
    selected = metrics["selected_model"]
    profile = Profile(
        source_tool=FACT_TOOL,
        subject="evaluation text",
        min_citations=MIN_CITATIONS_PER_TEXT,
        strict_numbers=True,
        dimensions=DIMENSIONS,
        text_checks=(lambda t: _claim_problems(t, selected),),
    )
    return check_text(text, facts, profile)
