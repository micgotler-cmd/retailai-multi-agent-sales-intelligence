"""Deterministic check of business insights against the EDA facts (P-04, M-02).

Agent 3 writes `insights.md` in its own words, but every number must be a fact
from `eda_summary.json`, written exactly as the fact's display value (sign,
decimals and % included). Two citation styles are accepted:

- individual: "Sunday averages 2.31 [F39] units per item per day"
- grouped:    "FOODS averages 2.23 units per item per day and has 74.2% of all
              units sold [F09, F11]"

A citation (or group) covers the numbers written since the previous citation in
the same paragraph or list item. Each such number must equal the display value
of a different cited fact. To stop a group from swapping meanings, a group may
not contain two facts with the same unit (two averages, two percentages, two
weekdays): those must be cited one by one. A unit word right after a number
("7 days") must match the fact's unit, and a cited weekday, month, item or date
fact must match the weekday, month, item or date written in its clause.
check_insights() returns the problems; an empty list means the text may be
saved. The LLM never computes or changes numbers (CLAUDE.md).

What a deterministic check cannot see: which words a correct, correctly cited
value is attached to. A wrong sentence around a right number remains possible
and is covered by the business review of the insights.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from src.data.eda import fmt

FACT_ID = re.compile(r"F\d{2,}")
_GROUP = r"\[\s*F\d{2,}(?:\s*[,;]\s*F\d{2,})*\s*\]"
GROUP = re.compile(rf"{_GROUP}(?:\s*{_GROUP})*")  # [F09, F11] or [F09][F11]
NUMBER = re.compile(r"(?<![\w.,])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![\w])")
HAS_DIGIT = re.compile(r"\d")
# Names and fixed references that contain digits but are not statistics.
ALLOWED = re.compile(
    r"\d{4}-\d{2}-\d{2}"  # ISO dates (a cited date fact is checked separately)
    r"|\bT-\d+\b|\b[DMOP]-\d+\b"  # decision, requirement and plan ids
    r"|\b[A-Z]+(?:_\d+)+\b"  # store and item ids (CA_1, FOODS_3_234)
    r"|\bd_\d+\b"  # M5 day ids
    r"|\bM5\b"  # dataset name
    r"|\b365\b"  # fixed trend window of the EDA method
    r"|\b25 December\b"  # the store-closure date (T-13)
    r"|" + _GROUP + r"|^\s*#+"  # fact ids themselves; Markdown headings
    r"|^\s*\d+[.)](?=\s)"  # numbered list markers
)
BLOCK_START = re.compile(r"^\s*(?:$|#|[-*+]\s|\d+[.)]\s|\|)")  # paragraph, heading, list, table

# Unit words that may follow a number, normalized to the first word of a fact unit.
UNIT_WORDS = {
    "item": "item",
    "items": "item",
    "day": "day",
    "days": "day",
    "unit": "unit",
    "units": "unit",
    "item-day": "item-day",
    "item-days": "item-day",
    "change": "change",
    "changes": "change",
    "week": "week",
    "weeks": "week",
    "month": "month",
    "months": "month",
    "year": "year",
    "years": "year",
}
NEXT_WORD = re.compile(r"\s*([A-Za-z][A-Za-z-]*)")
# A negative value followed by a "lower" word is a double negative ("-14.7% lower" reads
# as higher); third real run. The sign already says the direction.
DOWN_WORDS = {"lower", "less", "fewer", "below", "down", "smaller", "decrease", "decline", "drop"}

# Text facts: the words of the same kind written in a clause must match the cited fact.
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
MONTHS = (  # capitalized only, so the verb "may" is not a month
    "January|February|March|April|May|June|July|August|September|October|November|December"
    "|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
TEXT_KINDS = {
    "weekday": re.compile(rf"\b(?:{WEEKDAYS})\b"),
    "month": re.compile(rf"\b(?:{MONTHS})\b"),
    "item": re.compile(r"\b[A-Z]+_\d+_\d+\b"),
    "date": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
}

NEGATION = r"\b(?:not|no|never|cannot|can't|isn't|aren't|doesn't|don't|without)\b"
NON_CAUSAL = re.compile(
    rf"{NEGATION}[^.\n]{{0,60}}?\bcaus(?:al|ality|ation|e|es|ed|ing)\b", re.IGNORECASE
)
CAUSAL_TOPIC = re.compile(
    r"\b(?:snap|events?|holidays?|prices?|promotions?|discounts?)\b", re.IGNORECASE
)
CAUSAL_CLAIM = re.compile(
    r"\b(?:caus(?:e|es|ed|ing)|driv(?:e|es|en|ing)|leads? to|led to|results? in|resulted in"
    r"|due to|because of|thanks to|boost(?:s|ed|ing)?|impact of|effect of|trigger(?:s|ed)?)\b",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n")

MIN_CITATIONS = 5
MAX_CHARS = 20_000
EXAMPLE = "'2.31 [F39]' or '... 2.23 units per item per day and 74.2% of units [F09, F11]'"


@dataclass(frozen=True)
class Fact:
    """The parts of an EDA fact the check needs."""

    id: str
    display: str
    unit: str

    @property
    def numeric(self) -> bool:
        return bool(HAS_DIGIT.search(self.display)) and self.unit not in TEXT_KINDS

    @property
    def unit_word(self) -> str | None:
        """Normalized first word of the unit ('units/item/day' -> 'unit'), None for %."""
        return UNIT_WORDS.get(self.unit.split("/")[0])


def display_values(facts: list[dict]) -> dict[str, str]:
    """Fact id -> the exact text that must be written for it."""
    return {f["id"]: fmt(f["value"], f["unit"]) for f in facts}


def _facts(facts: list[dict]) -> dict[str, Fact]:
    return {f["id"]: Fact(f["id"], fmt(f["value"], f["unit"]), f["unit"]) for f in facts}


def _mask(text: str) -> str:
    """The text with allowed names and citations blanked out (same length and positions)."""
    lines = text.split("\n")
    return "\n".join(ALLOWED.sub(lambda m: " " * len(m.group(0)), line) for line in lines)


def _blocks(text: str) -> Iterator[tuple[int, int]]:
    """(start, end) of each paragraph, list item, heading or table row."""
    start, pos = 0, 0
    for line in text.split("\n"):
        if BLOCK_START.match(line) and pos > start:
            yield start, pos
            start = pos
        pos += len(line) + 1
    yield start, len(text)


def _short(text: str, size: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= size else text[: size - 3] + "..."


def _same_kind(a: str, b: str, kind: str) -> bool:
    if kind == "month":  # "April" matches the display "Apr"
        return a[:3].lower() == b[:3].lower()
    return a.lower() == b.lower()


def _check_clause(
    raw: str, masked: str, start: int, end: int, ids: list[str], facts: dict[str, Fact]
) -> list[str]:
    """Problems of the numbers and names written before one citation group."""
    problems = []
    label = "[" + ", ".join(ids) + "]"
    unknown = [i for i in ids if i not in facts]
    problems += [f"[{i}] does not exist; use only fact ids returned by run_eda" for i in unknown]
    cited = [facts[i] for i in dict.fromkeys(ids) if i in facts]
    by_unit: dict[str, list[str]] = {}
    for fact in cited:
        by_unit.setdefault(fact.unit, []).append(fact.id)
    for unit, same in by_unit.items():
        if len(same) > 1:
            problems.append(
                f"{label} groups facts with the same unit ({unit}: {', '.join(same)}), so the "
                f"values could be swapped; cite each one right after its value, for example "
                f"'{facts[same[0]].display} [{same[0]}] ... {facts[same[1]].display} [{same[1]}]'"
            )
    # Text facts: a weekday, month, item or date written here must be the cited one.
    clause = raw[start:end]
    for fact in cited:
        if fact.unit in TEXT_KINDS and len(by_unit[fact.unit]) == 1:  # else reported above
            for m in TEXT_KINDS[fact.unit].finditer(clause):
                if not _same_kind(m.group(0), fact.display, fact.unit):
                    problems.append(
                        f"{m.group(0)!r} before [{fact.id}] does not match the fact "
                        f"({fact.display!r}); write {fact.display!r} or cite the right fact"
                    )
    # Numbers: each one is the exact display value of a different cited fact.
    numeric = [f for f in cited if f.numeric]
    used: set[str] = set()
    for m in NUMBER.finditer(masked, start, end):
        value = m.group(0)
        match = [f for f in numeric if f.display == value and f.id not in used]
        word = NEXT_WORD.match(masked, m.end())
        word_unit = UNIT_WORDS.get(word.group(1).lower()) if word else None
        if word_unit:  # prefer the fact whose unit fits the word after the number
            match.sort(key=lambda f: f.unit_word != word_unit)
        if not match:
            expected = ", ".join(f"{f.display!r} [{f.id}]" for f in numeric) or "none"
            problems.append(
                f"{value!r} in '{_short(raw[start : m.end()])} {label}' is not the value of a "
                f"cited fact (cited values: {expected}); copy the display value exactly, "
                "including any minus sign and %"
            )
            continue
        fact = match[0]
        used.add(fact.id)
        if value.startswith("-") and word and word.group(1).lower() in DOWN_WORDS:
            problems.append(
                f"'{value} {word.group(1)}' is a double negative (it reads as higher); write "
                f"'a difference of {value} [{fact.id}]' or 'a {value} difference [{fact.id}]'"
            )
        if word_unit and fact.unit_word and word_unit != fact.unit_word:
            problems.append(
                f"'{value} {word.group(1)}' cites [{fact.id}], whose unit is {fact.unit!r}; "
                "use the unit of the fact or cite the right fact"
            )
    rest = NUMBER.sub(" ", masked[start:end])
    problems += [_uncited(t) for t in re.findall(r"\S*\d\S*", rest)]
    return problems


def _uncited(token: str) -> str:
    return (
        f"{token!r} is a number without a fact citation: write a fact's display value "
        f"followed by its id, for example {EXAMPLE}, or remove it"
    )


def _causal_problems(text: str) -> list[str]:
    problems = []
    if not NON_CAUSAL.search(text):
        problems.append(
            "Add a sentence saying SNAP, event and price findings are associations, "
            "not causal effects"
        )
    for sentence in SENTENCE_END.split(text):
        if (
            CAUSAL_TOPIC.search(sentence)
            and CAUSAL_CLAIM.search(sentence)
            and not re.search(NEGATION, sentence, re.IGNORECASE)
        ):
            problems.append(
                f"Causal claim in '{_short(sentence)}': describe it as an association "
                "(for example 'sales are higher on SNAP days'), not as a cause"
            )
    return problems


def check_insights(text: str, facts: list[dict]) -> list[str]:
    """Problems with an insights text; [] means every number is a correctly cited fact."""
    if not text.strip():
        return ["The insights are empty"]
    problems = []
    if len(text) > MAX_CHARS:
        problems.append(f"The insights are longer than {MAX_CHARS} characters")
    known = _facts(facts)
    masked = _mask(text)
    n_cited = 0
    for b_start, b_end in _blocks(text):
        pos = b_start
        for group in GROUP.finditer(text, b_start, b_end):
            ids = FACT_ID.findall(group.group(0))
            n_cited += len(ids)
            problems += _check_clause(text, masked, pos, group.start(), ids, known)
            pos = group.end()
        rest = NUMBER.sub(" ", masked[pos:b_end])  # after the last citation: uncited
        tail = [m.group(0) for m in NUMBER.finditer(masked, pos, b_end)]
        problems += [_uncited(t) for t in tail + re.findall(r"\S*\d\S*", rest)]
    if n_cited < MIN_CITATIONS:
        problems.append(f"Only {n_cited} cited facts; cite at least {MIN_CITATIONS}")
    problems += _causal_problems(text)
    return problems
