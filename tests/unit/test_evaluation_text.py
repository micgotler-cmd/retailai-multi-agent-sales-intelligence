"""Tests for the evaluation narrative check, the shared checker's profiles and the reports."""

from __future__ import annotations

import pytest

from src.data.insights_check import EDA_PROFILE, Profile, check_insights, check_text
from src.ml import evaluation_text as et
from src.ml import reports
from tests.ml_data import sample_metrics
from tests.unit.test_insights_check import CAUSAL, FACTS, GOOD, GROUPED


@pytest.fixture(scope="module")
def metrics():
    return sample_metrics()


def fact(metrics: dict, topic: str, key: str) -> tuple[str, str]:
    """(id, display) of one evaluation fact."""
    for f in et.build_facts(metrics):
        if (f["topic"], f["metric"]) == (topic, key):
            return f["id"], reports.fmt(f["value"], f["unit"])
    raise KeyError((topic, key))


def problems(text: str, metrics: dict) -> list[str]:
    return et.check_evaluation_text(text, metrics)


def has(found: list[str], fragment: str) -> bool:
    return any(fragment in p for p in found)


def cite(metrics: dict, topic: str, key: str) -> str:
    fact_id, shown = fact(metrics, topic, key)
    return f"{shown} [{fact_id}] units per item-day"


def padding(metrics: dict) -> str:
    """Two correct citations so a test sentence is not rejected for too few citations."""
    sel = metrics["selected_model"]
    return (
        f"\n\n{et.MODEL_NAMES[sel]} has a test MAE of {cite(metrics, 'test', f'{sel}_mae')} and a "
        f"test RMSE of {cite(metrics, 'test', f'{sel}_rmse')}."
    )


# --- regression: the Crew 1 behavior is unchanged --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        GOOD,
        GROUPED,
        "Sunday has 99.9 [F02] units.",  # wrong value
        "Store has 20 [F01] items and 5 uncited things.",
        "SNAP drives sales [F01]." + CAUSAL,
        "",
        "# Insights\n\n- 2.31 [F02] and 1.7 [F06] [F02, F06].",
    ],
)
def test_default_profile_gives_the_same_problems_as_check_insights(text):
    assert check_text(text, FACTS) == check_insights(text, FACTS)
    assert check_text(text, FACTS, EDA_PROFILE) == check_insights(text, FACTS)


def test_eda_profile_still_allows_free_dates_and_requires_the_non_causal_sentence():
    assert check_insights(GOOD, FACTS) == []  # contains the date 2016-03-27 uncited
    no_statement = "Store CA_1 has 20 [F01] items, 55,030 [F04] units, 2.31 [F02] units per item per day, 22.7% [F03] and 5 [F08] days."
    assert any("not causal" in p for p in check_insights(no_statement, FACTS))


def test_unknown_fact_message_names_the_tool_of_the_profile():
    eda = check_insights("Value 1 [F99].", FACTS)
    assert any("returned by run_eda" in p for p in eda)
    other = check_text("Value 1 [F99].", FACTS, Profile(source_tool="get_evaluation_facts"))
    assert any("returned by get_evaluation_facts" in p for p in other)


def test_a_profile_without_text_checks_has_no_causal_rule_but_evaluation_keeps_its_own(metrics):
    text = "SNAP days drive sales [F01]."
    plain = Profile(min_citations=1)
    assert not any("ausal" in p for p in check_text(text, FACTS, plain))  # the shared check is off
    claim = "Ridge wins because it uses lags and SNAP days drive sales."
    assert has(problems(claim, metrics), "Causal or explanatory claim")


# --- evaluation narrative: correct text passes ------------------------------------------------


def test_the_template_narrative_passes_the_check(metrics):
    narrative = reports.template_narrative(metrics)
    assert problems(narrative.summary, metrics) == []
    assert problems(narrative.interpretation, metrics) == []


def test_a_correct_hand_written_sentence_passes(metrics):
    sel = metrics["selected_model"]
    text = (
        f"{et.MODEL_NAMES[sel]} has a test MAE of {cite(metrics, 'test', f'{sel}_mae')}, "
        f"against Seasonal Naive's test MAE of {cite(metrics, 'test', 'seasonal_naive_mae')}."
    )
    assert problems(text, metrics) == []


# --- numbers tied to the right model, metric, period and group ----------------------------------


def test_a_value_attached_to_the_wrong_model_is_rejected(metrics):
    sel = metrics["selected_model"]
    ridge_value = cite(metrics, "test", f"{sel}_mae")
    text = f"Seasonal Naive has a test MAE of {ridge_value}." + padding(metrics)
    assert has(problems(text, metrics), "last model named")


def test_a_second_value_without_its_own_model_name_is_rejected(metrics):
    sel = metrics["selected_model"]
    text = (
        f"{et.MODEL_NAMES[sel]} has a test MAE of {cite(metrics, 'test', f'{sel}_mae')} "
        f"versus {cite(metrics, 'test', 'seasonal_naive_mae')}."
    )
    assert has(problems(text, metrics), "last model named")


def test_a_value_attached_to_the_wrong_metric_is_rejected(metrics):
    sel = metrics["selected_model"]
    text = f"{et.MODEL_NAMES[sel]} has a test RMSE of {cite(metrics, 'test', f'{sel}_mae')}."
    assert has(problems(text + padding(metrics), metrics), "last metric named")


def test_a_value_attached_to_the_wrong_period_is_rejected(metrics):
    sel = metrics["selected_model"]
    text = f"{et.MODEL_NAMES[sel]} has a backtest MAE of {cite(metrics, 'test', f'{sel}_mae')}."
    assert has(problems(text + padding(metrics), metrics), "last period named")
    ok = f"{et.MODEL_NAMES[sel]} has a backtest MAE of {cite(metrics, 'backtest', f'{sel}_mae')}."
    assert problems(ok + padding(metrics), metrics) == []


def test_the_model_metric_and_period_must_be_named(metrics):
    sel = metrics["selected_model"]
    shown = cite(metrics, "test", f"{sel}_mae")
    assert has(problems(f"The error is {shown}." + padding(metrics), metrics), "Name the model")
    text = f"{et.MODEL_NAMES[sel]} error is {shown}."
    found = problems(text + padding(metrics), metrics)
    assert has(found, "Name the metric") and has(found, "Name the period")


def test_demand_group_values_need_their_own_group(metrics):
    sel = metrics["selected_model"]
    name = et.MODEL_NAMES[sel]
    value = cite(metrics, "test_group", f"{sel}_high_mae")
    good = f"For the high-demand group, {name}'s test MAE is {value}."
    assert problems(good + padding(metrics), metrics) == []
    assert has(
        problems(f"{name}'s test MAE is {value}." + padding(metrics), metrics), "Name the group"
    )
    wrong = f"For the low-demand group, {name}'s test MAE is {value}."
    assert has(problems(wrong + padding(metrics), metrics), "last group named")
    overall = f"For the high-demand group, {name} has a test MAE of {cite(metrics, 'test', f'{sel}_mae')}."
    assert has(problems(overall + padding(metrics), metrics), "overall figure")


# --- unsupported claims -----------------------------------------------------------------------


def test_unknown_fact_ids_and_wrong_or_uncited_numbers_are_rejected(metrics):
    base = padding(metrics)
    assert has(problems("Ridge has a test MAE of 1.00 [F99]." + base, metrics), "does not exist")
    assert has(problems("Ridge has a test MAE of 9.99." + base, metrics), "without a fact citation")
    sel = metrics["selected_model"]
    wrong = (
        f"{et.MODEL_NAMES[sel]} has a test MAE of 9.99 [{fact(metrics, 'test', f'{sel}_mae')[0]}]."
    )
    assert has(problems(wrong + base, metrics), "not the value of a cited fact")


def test_dates_and_day_ids_need_a_citation_in_evaluation_text(metrics):
    assert has(
        problems("The test window is 2016-04-25 to 2016-05-22." + padding(metrics), metrics),
        "without a fact citation",
    )
    assert has(
        problems("The refit runs through d_1941." + padding(metrics), metrics),
        "without a fact citation",
    )


def test_causal_and_explanatory_claims_are_rejected_for_any_topic(metrics):
    for claim in (
        "Ridge wins because it uses lag features.",
        "The error is driven by the zero-sales days.",
        "Random Forest overfits, which explains its larger error.",
        "SNAP days lead to higher sales.",
    ):
        assert has(problems(claim + padding(metrics), metrics), "explanatory claim"), claim
    negated = "This report does not explain why a model performs as it does."
    assert not has(problems(negated + padding(metrics), metrics), "explanatory claim")


def test_comparisons_need_a_cited_fact_in_the_same_sentence(metrics):
    sel = metrics["selected_model"]
    assert has(
        problems("Ridge is better than Seasonal Naive." + padding(metrics), metrics),
        "without a cited fact",
    )
    cited = f"{et.MODEL_NAMES[sel]} is better, with a test MAE of {cite(metrics, 'test', f'{sel}_mae')}."
    assert problems(cited + padding(metrics), metrics) == []


def test_the_selection_cannot_be_contested(metrics):
    sel = metrics["selected_model"]
    other = "Random Forest" if sel == "ridge" else "Ridge"
    assert has(
        problems(f"{other} was selected as the final model." + padding(metrics), metrics),
        "another model was selected",
    )
    assert not has(
        problems(f"{other} was not selected." + padding(metrics), metrics), "another model"
    )
    assert not has(
        problems(f"{et.MODEL_NAMES[sel]} was selected." + padding(metrics), metrics),
        "another model",
    )


def test_significance_guarantees_and_promises_are_rejected(metrics):
    for claim in (
        "The improvement is statistically significant.",
        "Ridge guarantees accurate forecasts.",
        "Ridge will outperform Seasonal Naive next month.",
    ):
        assert has(problems(claim + padding(metrics), metrics), "Unsupported claim"), claim


def test_too_few_citations_and_empty_text_are_rejected(metrics):
    sel = metrics["selected_model"]
    one = f"{et.MODEL_NAMES[sel]} has a test MAE of {cite(metrics, 'test', f'{sel}_mae')}."
    assert has(problems(one, metrics), "Only 1 cited facts")
    assert has(problems("", metrics), "empty")


# --- reports -----------------------------------------------------------------------------------


def sections(text: str) -> dict[str, str]:
    parts = text.split("\n## ")[1:]
    return {p.split("\n", 1)[0]: p for p in parts}


def test_report_separates_backtest_test_and_refit(metrics):
    narrative = reports.template_narrative(metrics)
    report = reports.render_evaluation_report(metrics, narrative, "agent")
    named = sections(report)
    backtest = next(v for k, v in named.items() if k.startswith("3."))
    test = next(v for k, v in named.items() if k.startswith("4."))
    refit = next(v for k, v in named.items() if k.startswith("5."))
    assert "comparison and tuning only" in backtest and "scored once" in test
    assert "not evaluated" in refit and metrics["refit"]["model_version"] in refit
    sel = metrics["selected_model"]
    f = reports._f
    assert f(metrics["models"][sel]["backtest"]["mean_overall"]["mae"]) in backtest
    assert f(metrics["test"]["overall"]["mae"]) in test
    assert f(metrics["test"]["overall"]["mae"]) not in backtest  # test numbers stay out of 3
    assert f(metrics["models"][sel]["backtest"]["mean_overall"]["mae"]) not in test
    assert "were not recomputed" in refit
    for item in metrics["test"]["per_item"]:
        assert item in test


def test_report_prints_the_grids_selection_rule_and_limitations(metrics):
    report = reports.render_evaluation_report(metrics, reports.template_narrative(metrics), "agent")
    assert metrics["selection"]["metric"] in report
    assert "Hyperparameter grids" in report and "alpha" in report and "n_estimators" in report
    assert "Intermittent demand" in report and "No inventory data" in report
    assert "no causal claims" in report
    assert "does not guarantee" in report and "person must review" in report  # human review


def test_fallback_reports_are_labeled_and_agent_reports_are_not(metrics):
    narrative = reports.template_narrative(metrics)
    for render in (reports.render_evaluation_report, reports.render_model_card):
        fallback = render(metrics, narrative, "template", "the citation check rejected 3 attempts")
        assert fallback.startswith(reports.FALLBACK_MARKER)
        assert "Fallback" in fallback and "citation check rejected 3 attempts" in fallback
        agent = render(metrics, narrative, "agent")
        assert agent.startswith(reports.AGENT_MARKER) and "Fallback" not in agent
        with pytest.raises(ValueError):
            render(metrics, narrative, "somebody")


def test_the_narrative_is_inserted_verbatim_and_the_model_card_is_complete(metrics):
    narrative = reports.Narrative("SUMMARY-TEXT-123", "INTERPRETATION-TEXT-456")
    report = reports.render_evaluation_report(metrics, narrative, "agent")
    card = reports.render_model_card(metrics, narrative, "agent")
    assert "SUMMARY-TEXT-123" in report and "INTERPRETATION-TEXT-456" in report
    assert "SUMMARY-TEXT-123" in card
    for heading in (
        "Purpose",
        "Training data",
        "Model",
        "Evaluation",
        "Limitations",
        "Ethical considerations",
        "Reproducibility",
    ):
        assert f"## {heading}" in card
    assert metrics["refit"]["model_version"] in card
    assert "`sell_price` is not used" in card
