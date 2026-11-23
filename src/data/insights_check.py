"""Deterministic check of business insights against the EDA facts (P-04, M-02).

Agent 3 writes `insights.md` in its own words, but every number must be a fact
from `eda_summary.json`, written exactly as the fact's display value and
followed by its id, for example "2.31 [F39]". check_insights() returns the
problems; an empty list means the text may be saved. The LLM never computes or
changes numbers (CLAUDE.md).
"""

from __future__ import annotations

import re

from src.data.eda import fmt

CITED = re.compile(r"(\S+) \[(F\d{2,})\]")
HAS_DIGIT = re.compile(r"\d")
# Names and fixed references that contain digits but are not statistics.
ALLOWED = re.compile(
    r"\d{4}-\d{2}-\d{2}"  # ISO dates
    r"|\bT-\d+\b|\b[DMO]-\d+\b"  # decision and requirement ids
    r"|\b[A-Z]+(?:_\d+)+\b"  # store and item ids (CA_1, FOODS_3_234)
    r"|\bd_\d+\b"  # M5 day ids
    r"|\bM5\b"  # dataset name
    r"|\b365\b"  # fixed trend window of the EDA method
    r"|\b25 December\b"  # the store-closure date (T-13)
    r"|\[F\d{2,}\]"  # fact ids themselves
    r"|^#+"  # Markdown headings
)
REQUIRED_PHRASE = "not causal"
MIN_CITATIONS = 5
MAX_CHARS = 20_000


def display_values(facts: list[dict]) -> dict[str, str]:
    """Fact id -> the exact text that must appear before its citation."""
    return {f["id"]: fmt(f["value"], f["unit"]) for f in facts}


def check_insights(text: str, facts: list[dict]) -> list[str]:
    """Problems with an insights text; [] means every number is a correctly cited fact."""
    problems = []
    if not text.strip():
        return ["The insights are empty"]
    if len(text) > MAX_CHARS:
        problems.append(f"The insights are longer than {MAX_CHARS} characters")
    shown = display_values(facts)
    cited = CITED.findall(text)
    if len(cited) < MIN_CITATIONS:
        problems.append(f"Only {len(cited)} cited facts; cite at least {MIN_CITATIONS}")
    for value, fact_id in cited:
        value = value.strip("(,;:).")
        if fact_id not in shown:
            problems.append(f"[{fact_id}] does not exist; use only fact ids returned by run_eda")
        elif value != shown[fact_id] and HAS_DIGIT.search(value):
            # A number right before a citation must be the fact's exact display value.
            # A word before a citation ("zero sales [F07]") is a reference: no number is shown.
            problems.append(
                f"The number before [{fact_id}] must be exactly {shown[fact_id]!r} "
                f"(write '{shown[fact_id]} [{fact_id}]'), found {value!r}"
            )
    rest = CITED.sub("", text)
    rest = "\n".join(ALLOWED.sub("", line) for line in rest.splitlines())
    for match in re.finditer(r"[^\s]*\d[^\s]*", rest):
        problems.append(
            f"{match.group(0)!r} is a number without a fact citation: replace it with a fact's "
            "display value followed by its id, or remove it"
        )
    if REQUIRED_PHRASE not in text.lower():
        problems.append(
            f"Add a sentence saying SNAP, event and price findings are associations, "
            f"{REQUIRED_PHRASE} effects"
        )
    return problems
