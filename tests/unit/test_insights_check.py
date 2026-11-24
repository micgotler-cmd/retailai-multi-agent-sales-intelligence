"""Tests for the insights citation check: both citation styles, exact values, swaps, causality."""

from __future__ import annotations

import pytest

from src.data.insights_check import check_insights

FACTS = [
    {"id": "F01", "value": 20, "unit": "items"},
    {"id": "F02", "value": 2.3123, "unit": "units/item/day"},  # SNAP days
    {"id": "F03", "value": 22.71, "unit": "%"},
    {"id": "F04", "value": 55030, "unit": "units"},
    {"id": "F05", "value": "Sunday", "unit": "weekday"},
    {"id": "F06", "value": 1.7, "unit": "units/item/day"},  # other days
    {"id": "F07", "value": -14.72, "unit": "%"},
    {"id": "F08", "value": 5, "unit": "days"},
    {"id": "F09", "value": "Thursday", "unit": "weekday"},
    {"id": "F10", "value": "Apr", "unit": "month"},
]
CAUSAL = " These are associations, not causal effects."
GOOD = (  # individual citations
    "# Insights\n\nStore CA_1 has 20 [F01] items. Sunday [F05] is busiest at 2.31 [F02] "
    "units per item per day; 55,030 [F04] units in total. SNAP days are 22.7% [F03] higher, "
    "an association, not causal. FOODS_3_234 is an item; the period ends 2016-03-27 (T-09)."
)
GROUPED = (
    "# Insights\n\n"
    "- On SNAP days items sell 2.31 units per item per day, 22.7% more [F02, F03].\n"
    "- The store has 20 items and sold 55,030 units [F01, F04].\n"
    "- Sunday is the busiest day at 2.31 units per item per day [F05][F02].\n"
    "- National events: -14.7% [F07]; the store was closed on 5 days [F08]." + CAUSAL
)


def problems(text: str) -> list[str]:
    return check_insights(text, FACTS)


def has(text: str, fragment: str) -> bool:
    return any(fragment in p for p in problems(text))


# ------------------------------------------------------------ accepted texts


@pytest.mark.parametrize("text", [GOOD, GROUPED], ids=["individual", "grouped"])
def test_both_citation_styles_are_accepted(text):
    assert problems(text) == []


def test_grouped_ids_may_be_in_any_order_when_units_differ():
    text = GROUPED.replace("[F02, F03]", "[F03, F02]")
    assert problems(text) == []


def test_citation_after_a_word_is_a_reference():
    """First real run: 'excluded due to zero sales [F07]' shows no number, so it is allowed."""
    assert problems(GOOD + " Closure days are excluded because of zero sales [F08].") == []


def test_month_name_matches_its_abbreviation():
    assert problems(GOOD + "\n\nApril is the strongest month [F10].") == []


def test_numbered_list_markers_are_not_numbers():
    assert problems(GOOD + "\n\n1. Stock up before weekends.\n2. Watch SNAP days.") == []


@pytest.mark.parametrize(
    "wording",
    [
        "These are associations, not causal effects.",
        "The findings should not be interpreted as causal effects.",
        "They do not imply causation.",
        "There is no causal evidence here.",
        "SNAP does not cause the higher sales; it is an association.",
    ],
)
def test_non_causal_wording_is_accepted(wording):
    text = GOOD.replace("an association, not causal", "an association") + " " + wording
    assert problems(text) == []


# ------------------------------------------------------------ wrong values


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("2.31 [F02]", "2.40 [F02]"),  # changed value
        ("2.31 [F02]", "2.3 [F02]"),  # rounded
        ("22.7% [F03]", "22.7 [F03]"),  # unit % dropped
        ("22.7% [F03]", "-22.7% [F03]"),  # sign added
        ("22.7% [F03]", "23% [F03]"),
    ],
)
def test_changed_values_are_rejected(old, new):
    assert has(GOOD.replace(old, new), "is not the value of a cited fact")


def test_sign_must_be_kept():
    """Second real run: '14.7% lower' for the fact '-14.7%'."""
    text = GROUPED.replace("-14.7% [F07]", "a 14.7% lower average [F07]")
    found = problems(text)
    assert any("'14.7%'" in p and "'-14.7%' [F07]" in p and "minus sign" in p for p in found)


@pytest.mark.parametrize("word", ["lower", "less", "below", "decline"])
def test_negative_value_with_a_down_word_is_rejected(word):
    """Third real run: 'National events ... -14.7% lower than days without events'."""
    text = GROUPED.replace("-14.7% [F07]", f"-14.7% {word} than other days [F07]")
    assert has(text, f"'-14.7% {word}' is a double negative")


@pytest.mark.parametrize(
    "wording",
    ["a difference of -14.7% [F07]", "a -14.7% [F07] difference", "-14.7% [F07] versus other days"],
)
def test_negative_value_without_a_down_word_is_accepted(wording):
    assert problems(GROUPED.replace("-14.7% [F07]", wording)) == []


def test_wrong_value_in_a_group_is_rejected():
    text = GROUPED.replace("22.7% more [F02, F03]", "25.0% more [F02, F03]")
    assert has(text, "'25.0%'")


# ------------------------------------------------------------ swapped facts


def test_group_with_two_facts_of_the_same_unit_is_rejected():
    """'2.31 on SNAP days versus 1.70 on other days [F02, F06]' could be read either way."""
    text = GOOD + "\n\n- SNAP days 2.31 versus other days 1.70 units per item per day [F02, F06]."
    assert has(text, "groups facts with the same unit (units/item/day: F02, F06)")
    swapped = text.replace("2.31 versus other days 1.70", "1.70 versus other days 2.31")
    assert has(swapped, "groups facts with the same unit")


def test_value_of_another_fact_is_rejected():
    """The value is real, but it belongs to F06, not to the cited F02."""
    assert has(GOOD.replace("2.31 [F02]", "1.70 [F02]"), "is not the value of a cited fact")


def test_extra_number_in_a_clause_is_rejected():
    text = GOOD + "\n\n- SNAP days 2.31 and other days 1.70 units [F02]."
    assert has(text, "'1.70'")


def test_unit_word_must_match_the_fact():
    assert has(GOOD.replace("20 [F01] items", "20 [F01] days"), "whose unit is 'items'")
    text = GROUPED.replace("closed on 5 days [F08]", "closed for 5 items [F08]")
    assert has(text, "whose unit is 'days'")


@pytest.mark.parametrize(
    ("old", "new", "fragment"),
    [
        ("Sunday [F05] is busiest", "Thursday [F05] is busiest", "'Thursday' before [F05]"),
        (
            "Sunday is the busiest day at 2.31 units per item per day [F05][F02]",
            "Thursday is the busiest day at 2.31 units per item per day [F05][F02]",
            "'Thursday' before [F05]",
        ),
    ],
)
def test_wrong_weekday_is_rejected(old, new, fragment):
    text = (GOOD + "\n\n" + GROUPED).replace(old, new)
    assert has(text, fragment)


def test_two_weekdays_in_one_group_are_rejected():
    text = GOOD + "\n\n- Thursday is quietest and Sunday busiest [F05, F09]."
    assert has(text, "groups facts with the same unit (weekday: F05, F09)")


# ------------------------------------------------- ids, uncited numbers, form


@pytest.mark.parametrize(
    "text",
    [GOOD.replace("[F04]", "[F99]"), GROUPED.replace("[F01, F04]", "[F01, F99]")],
    ids=["individual", "grouped"],
)
def test_unknown_fact_ids_are_rejected(text):
    assert has(text, "[F99] does not exist")


@pytest.mark.parametrize(
    "extra",
    [" Expect 10% growth.", "\n\n- 3 new items next month.", " Up 7%."],
)
def test_uncited_numbers_are_rejected(extra):
    found = problems(GOOD + extra)
    assert any("is a number without a fact citation" in p for p in found)
    assert any("[F09, F11]" in p for p in found)  # the message shows both styles


def test_number_in_another_list_item_is_not_covered_by_a_later_citation():
    text = GROUPED.replace("[F01, F04].\n", "and 55,030 units.\n- Sunday [F05].\n")
    assert has(text, "'55,030' is a number without a fact citation")


@pytest.mark.parametrize(
    ("text", "fragment"),
    [("", "empty"), ("Only 20 [F01] items, not causal.", "cite at least")],
)
def test_form_problems(text, fragment):
    assert has(text, fragment)


# ---------------------------------------------------------------- causality


def test_missing_non_causal_statement_is_rejected():
    assert has(GOOD.replace("not causal", "a clear effect"), "not causal effects")


@pytest.mark.parametrize(
    "claim",
    [
        "SNAP days drive higher sales.",
        "Higher prices lead to lower sales.",
        "Events cause a drop in demand.",
        "Sales rise due to SNAP benefits.",
        "The holiday boosts sales.",
    ],
)
def test_causal_claims_are_rejected(claim):
    assert has(GOOD + " " + claim, "Causal claim in")


def test_non_causal_sentences_with_cause_words_are_accepted():
    """'because of' without SNAP, events or prices is a method note, not a causal claim."""
    assert problems(GOOD + " Christmas is excluded because of the store closure.") == []
