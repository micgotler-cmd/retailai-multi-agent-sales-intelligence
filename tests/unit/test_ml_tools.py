"""Tests for the Crew 2 tools: prerequisites, stale outputs, fixed selection, the narrative
gate and run-folder binding. Synthetic data only, no LLM."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.ml import models, reports
from src.tools import data_tools as dt
from src.tools import ml_tools as mt
from src.tools.data_tools import ToolRefused
from tests.conftest import ITEMS, write_scope_file


@pytest.fixture(autouse=True)
def small_grids(monkeypatch):
    monkeypatch.setattr(
        models,
        "GRIDS",
        {
            models.RIDGE: {"alpha": [1.0, 100.0]},
            models.RANDOM_FOREST: {
                "n_estimators": [10],
                "max_depth": [3, 6],
                "min_samples_leaf": [5],
            },
        },
    )


@pytest.fixture
def paths(m5_raw_dir: Path, tmp_path: Path) -> dt.RunPaths:
    """A run folder holding the outputs of Crew 1 (built by the real Crew 1 tools)."""
    scope = write_scope_file(tmp_path / "scope.json", ITEMS)
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    run_paths = dt.RunPaths(m5_raw_dir, scope, run_dir)
    for tool in (dt.ValidateRawDataTool, dt.BuildCleanDataTool, dt.WriteContractTool):
        json.loads(tool(paths=run_paths).run())
    return run_paths


def run(tool_cls, paths, **kwargs) -> dict:
    return json.loads(tool_cls(paths=paths).run(**kwargs))


def refused(tool_cls, paths, **kwargs) -> str:
    with pytest.raises(ToolRefused) as info:
        tool_cls(paths=paths)._run(**kwargs)
    return str(info.value)


@pytest.fixture
def trained(paths):
    run(mt.BuildFeaturesTool, paths)
    return run(mt.TrainModelsTool, paths)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Agent 4: features -------------------------------------------------------------------------


def test_build_features_rechecks_the_contract_and_returns_counts_not_rows(paths):
    out = run(mt.BuildFeaturesTool, paths)
    assert out["contract_recheck"] == "pass"
    assert paths.out(mt.CONTRACT_RECHECK).is_file() and paths.out(mt.FEATURES).is_file()
    table = pd.read_csv(paths.out(mt.FEATURES))
    assert out["rows"] == len(table) and out["future_rows"] == 28 * len(ITEMS)
    assert out["price_feature_used"] is False and out["longest_lookback_days"] == 55
    assert "sell_price" not in out["required_features"]
    assert "units_sold" not in json.dumps(out)  # no data rows go to the LLM


def test_build_features_refuses_without_gate_1_evidence(paths):
    paths.out(dt.CONTRACT_CHECK).unlink()
    assert "Missing earlier output" in refused(mt.BuildFeaturesTool, paths)
    assert not paths.out(mt.FEATURES).exists()


def test_build_features_refuses_when_gate_1_failed(paths):
    failed = json.loads(paths.out(dt.CONTRACT_CHECK).read_text())
    failed["status"] = "fail"
    paths.out(dt.CONTRACT_CHECK).write_text(json.dumps(failed))
    assert "Gate 1 did not pass" in refused(mt.BuildFeaturesTool, paths)
    assert not paths.out(mt.FEATURES).exists()


def test_build_features_refuses_when_the_clean_data_no_longer_matches_the_contract(paths):
    clean = pd.read_csv(paths.out(dt.CLEAN_DATA))
    clean.loc[0, "units_sold"] = -5  # outside the contract range
    clean.to_csv(paths.out(dt.CLEAN_DATA), index=False)
    assert "no longer matches the contract" in refused(mt.BuildFeaturesTool, paths)
    assert not paths.out(mt.FEATURES).exists()
    assert not paths.out(mt.CONTRACT_RECHECK).exists()  # a failed re-check leaves no file


def test_refusals_are_logged_with_their_reason(paths, caplog):
    failed = json.loads(paths.out(dt.CONTRACT_CHECK).read_text())
    failed["status"] = "fail"
    paths.out(dt.CONTRACT_CHECK).write_text(json.dumps(failed))
    with caplog.at_level("WARNING", logger="src.tools.ml_tools"):
        refused(mt.BuildFeaturesTool, paths)
    assert "build_features refused in run run-1: Gate 1 did not pass" in caplog.text


def test_build_features_clears_stale_downstream_outputs_first(paths):
    for name in mt.CREW2_OUTPUTS:
        paths.out(name).write_text("STALE")
    paths.out(dt.CONTRACT_CHECK).unlink()  # make the build fail after the clearing
    refused(mt.BuildFeaturesTool, paths)
    assert [n for n in mt.CREW2_OUTPUTS if paths.out(n).exists()] == []


# --- Agent 5: training ---------------------------------------------------------------------------


def test_train_models_writes_the_outputs_and_hides_test_scores(trained, paths):
    for name in mt.TRAIN_OUTPUTS:
        assert paths.out(name).is_file()
    metrics = json.loads(paths.out(mt.METRICS).read_text())
    assert metrics["run_id"] == "run-1" and trained["selected_model"] == metrics["selected_model"]
    assert trained["model_version"] == metrics["refit"]["model_version"]
    assert trained["selection_metric"].startswith("mean overall MAE")
    assert "test" not in trained and "improvement" not in json.dumps(trained)  # no test scores
    assert trained["n_candidates"] == 4 and trained["refit_fitted_through_day"] == 200


def test_the_model_selection_is_fixed_and_cannot_be_overridden(paths, trained):
    metrics_before = digest(paths.out(mt.METRICS))
    other = "random_forest" if trained["selected_model"] == "ridge" else "ridge"
    again = run(mt.TrainModelsTool, paths, selected_model=other, alpha=0.0, n_estimators=1)
    assert again["selected_model"] == trained["selected_model"]  # arguments are ignored
    assert digest(paths.out(mt.METRICS)) == metrics_before  # same deterministic result


def test_train_models_refuses_without_features_or_a_passed_recheck(paths):
    assert "Missing earlier output" in refused(mt.TrainModelsTool, paths)
    run(mt.BuildFeaturesTool, paths)
    failed = json.loads(paths.out(mt.CONTRACT_RECHECK).read_text())
    failed["status"] = "fail"
    paths.out(mt.CONTRACT_RECHECK).write_text(json.dumps(failed))
    assert "re-check did not pass" in refused(mt.TrainModelsTool, paths)
    assert [n for n in mt.TRAIN_OUTPUTS if paths.out(n).exists()] == []


def test_train_models_rejects_invalid_features_and_leaves_no_outputs(paths):
    run(mt.BuildFeaturesTool, paths)
    table = pd.read_csv(paths.out(mt.FEATURES), keep_default_na=False, na_values=[""])
    table = table.drop(columns="lag_28")
    table.to_csv(paths.out(mt.FEATURES), index=False)
    assert "FeatureError" in refused(mt.TrainModelsTool, paths)
    assert [n for n in mt.TRAIN_OUTPUTS if paths.out(n).exists()] == []


def test_train_models_clears_stale_outputs_of_an_earlier_attempt(paths, trained):
    paths.out(mt.EVALUATION_REPORT).write_text("STALE")
    paths.out(mt.FEATURES).unlink()
    refused(mt.TrainModelsTool, paths)
    assert [n for n in [*mt.TRAIN_OUTPUTS, *mt.REPORT_OUTPUTS] if paths.out(n).exists()] == []


# --- Agent 6: facts and narrative -------------------------------------------------------------------


def test_evaluation_facts_come_from_this_runs_metrics_only(trained, paths):
    out = run(mt.GetEvaluationFactsTool, paths)
    assert out["selected_model"] == trained["selected_model"]
    assert set(out["periods"]) == {"backtest", "test", "refit"}
    first = out["facts"][0]
    assert {"id", "display", "unit", "labels", "definition"} <= set(first)
    assert paths.out(mt.EVALUATION_FACTS).is_file()
    assert "units_sold" not in json.dumps(out)
    metrics = json.loads(paths.out(mt.METRICS).read_text())
    metrics["run_id"] = "another-run"  # a stale file copied from another run
    paths.out(mt.METRICS).write_text(json.dumps(metrics))
    assert "another run" in refused(mt.GetEvaluationFactsTool, paths)
    metrics["run_id"], metrics["schema_version"] = "run-1", "1.0.0"
    paths.out(mt.METRICS).write_text(json.dumps(metrics))
    assert "schema version" in refused(mt.GetEvaluationFactsTool, paths)


def test_facts_tool_refuses_without_metrics(paths):
    assert "Missing earlier output" in refused(mt.GetEvaluationFactsTool, paths)


def good_narrative(paths) -> reports.Narrative:
    return reports.template_narrative(json.loads(paths.out(mt.METRICS).read_text()))


def save(paths, narrative: reports.Narrative) -> dict:
    return run(
        mt.SaveEvaluationNarrativeTool,
        paths,
        summary=narrative.summary,
        interpretation=narrative.interpretation,
    )


def test_a_checked_narrative_writes_both_documents_with_python_tables(trained, paths):
    metrics_hash = digest(paths.out(mt.METRICS))
    assert save(paths, good_narrative(paths)) == {"saved": True}
    report = paths.out(mt.EVALUATION_REPORT).read_text()
    card = paths.out(mt.MODEL_CARD).read_text()
    assert report.startswith(reports.AGENT_MARKER) and card.startswith(reports.AGENT_MARKER)
    assert "| Model | Mean MAE" in report  # a table rendered by Python
    assert digest(paths.out(mt.METRICS)) == metrics_hash  # the agent cannot change the metrics
    assert not list(paths.run_dir.glob("*.tmp"))
    attempts = mt.read_evaluation_attempts(paths)
    assert len(attempts) == 1 and attempts[0]["saved"] is True


def test_a_rejected_narrative_writes_no_documents_and_is_recorded(trained, paths):
    bad = reports.Narrative("Ridge is better because it uses lags 1.00.", "Nothing cited.")
    out = save(paths, bad)
    assert out["saved"] is False and out["problem_count"] >= 2 and out["attempts_left"] == 2
    assert any(p.startswith("summary:") for p in out["problems"])
    assert not paths.out(mt.EVALUATION_REPORT).exists() and not paths.out(mt.MODEL_CARD).exists()
    assert mt.read_evaluation_attempts(paths)[0]["saved"] is False


def test_a_stale_report_cannot_survive_a_rejected_attempt(trained, paths):
    paths.out(mt.EVALUATION_REPORT).write_text("STALE")
    paths.out(mt.MODEL_CARD).write_text("STALE")
    save(paths, reports.Narrative("No facts at all.", "None."))
    assert not paths.out(mt.EVALUATION_REPORT).exists() and not paths.out(mt.MODEL_CARD).exists()


def test_attempts_are_capped_and_a_late_good_text_is_refused(trained, paths):
    bad = reports.Narrative("No facts.", "No facts.")
    for _ in range(dt.MAX_SAVE_ATTEMPTS):
        assert save(paths, bad)["saved"] is False
    out = save(paths, good_narrative(paths))
    assert out["saved"] is False and out["attempts_left"] == 0
    assert not paths.out(mt.EVALUATION_REPORT).exists()


def test_a_narrative_cannot_name_another_model_as_selected(trained, paths):
    sel = trained["selected_model"]
    other = "Random Forest" if sel == "ridge" else "Ridge"
    narrative = good_narrative(paths)
    forged = reports.Narrative(
        narrative.summary, narrative.interpretation + f"\n- {other} was selected."
    )
    out = save(paths, forged)
    assert out["saved"] is False and any("another model was selected" in p for p in out["problems"])


def test_template_fallback_writes_labeled_documents(trained, paths):
    mt.write_template_reports(paths, "the agent did not call save_evaluation_narrative")
    for name in (mt.EVALUATION_REPORT, mt.MODEL_CARD):
        text = paths.out(name).read_text()
        assert text.startswith(reports.FALLBACK_MARKER)
        assert "did not call save_evaluation_narrative" in text


def test_the_documents_hold_no_row_level_sales(trained, paths):
    mt.write_template_reports(paths, "test")
    clean = pd.read_csv(paths.out(dt.CLEAN_DATA))
    text = paths.out(mt.EVALUATION_REPORT).read_text() + paths.out(mt.MODEL_CARD).read_text()
    assert "units_sold" not in text
    assert str(clean["date"].iloc[5]) not in text  # no row dates from the sales file


# --- binding to the run folder ---------------------------------------------------------------------------


def test_tools_write_only_inside_their_run_folder(paths):
    outside = [p for p in paths.run_dir.parents[1].rglob("*") if p.is_file()]
    before = {p: digest(p) for p in outside if paths.run_dir not in p.parents}
    run(mt.BuildFeaturesTool, paths)
    run(mt.TrainModelsTool, paths)
    run(mt.GetEvaluationFactsTool, paths)
    save(paths, good_narrative(paths))
    after = {
        p: digest(p)
        for p in paths.run_dir.parents[1].rglob("*")
        if p.is_file() and paths.run_dir not in p.parents
    }
    assert after == before  # raw files, scope and other folders untouched
    assert set(mt.CREW2_OUTPUTS) <= {p.name for p in paths.run_dir.iterdir()}


def test_no_tool_takes_a_path_or_model_argument(paths):
    for tool_cls in (mt.BuildFeaturesTool, mt.TrainModelsTool, mt.GetEvaluationFactsTool):
        fields = set(tool_cls(paths=paths).args_schema.model_fields)
        assert not fields & {"path", "file", "model", "selected_model", "alpha"}
    assert set(mt.SaveEvaluationNarrativeTool(paths=paths).args_schema.model_fields) == {
        "summary",
        "interpretation",
    }


def test_each_agent_gets_only_its_own_tools(paths):
    assert [t.name for t in mt.feature_tools(paths)] == ["build_features"]
    assert [t.name for t in mt.trainer_tools(paths)] == ["train_models"]
    assert [t.name for t in mt.evaluator_tools(paths)] == [
        "get_evaluation_facts",
        "save_evaluation_narrative",
    ]
