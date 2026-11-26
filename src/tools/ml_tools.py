"""CrewAI tools for Crew 2 (Data Scientist). Thin wrappers; all logic lives in src/ml.

Like the Crew 1 tools, each tool is created for one run (`RunPaths`), so an agent never
chooses a file, and tools return short JSON summaries (counts, scores, fact text), never data
rows (T-04). Model selection is computed by `src.ml.train`; no tool takes a model choice or a
hyperparameter, and the evaluator's tools only read `metrics.json`.

Stale results cannot be mistaken for current ones: every tool first deletes its own outputs
and everything downstream of them, runs only when its inputs are present, and removes its
outputs again if it fails. `metrics.json` must carry this run's id.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from src.data import contract
from src.data.cleaning import CleaningError
from src.data.eda import fmt
from src.data.scope import ScopeError, load_scope
from src.ml import evaluate_baseline as baseline_eval
from src.ml import evaluation_text, reports, train
from src.ml import feature_spec as spec
from src.ml import features as ft
from src.ml.baseline import HistoryError
from src.ml.feature_spec import FeatureError
from src.ml.metrics import MetricsError
from src.ml.models import ModelError
from src.ml.windows import WindowError
from src.tools.data_tools import (
    CLEAN_DATA,
    CONTRACT,
    CONTRACT_CHECK,
    MAX_PROBLEMS_SHOWN,
    MAX_SAVE_ATTEMPTS,
    RunPaths,
    ToolRefused,
    _json,
    _read_json,
    _require,
    _RunTool,
)

FEATURES = "features.csv"
CONTRACT_RECHECK = "contract_recheck.json"
MODEL = train.MODEL_FILE
METRICS = train.METRICS_FILE
TEST_FORECAST = train.TEST_FORECAST_FILE
FORECAST = train.FORECAST_FILE
EVALUATION_FACTS = "evaluation_facts.json"
EVALUATION_ATTEMPTS = "evaluation_attempts.json"
EVALUATION_REPORT = "evaluation_report.md"
MODEL_CARD = "model_card.md"

FEATURE_OUTPUTS = [FEATURES, CONTRACT_RECHECK]
TRAIN_OUTPUTS = [MODEL, METRICS, TEST_FORECAST, FORECAST]
REPORT_OUTPUTS = [EVALUATION_FACTS, EVALUATION_ATTEMPTS, EVALUATION_REPORT, MODEL_CARD]
CREW2_OUTPUTS = [*FEATURE_OUTPUTS, *TRAIN_OUTPUTS, *REPORT_OUTPUTS]
DOMAIN_ERRORS = (
    FeatureError,
    ModelError,
    MetricsError,
    HistoryError,
    WindowError,
    CleaningError,
    ScopeError,
    baseline_eval.EvaluationError,
    OSError,
)
logger = logging.getLogger(__name__)


def clear_outputs(paths: RunPaths, names: Iterable[str]) -> None:
    """Delete these outputs (and leftover temp files) from the run folder."""
    for name in names:
        for path in (paths.out(name), paths.out(f"{name}.tmp")):
            path.unlink(missing_ok=True)


def _run_id(paths: RunPaths) -> str:
    return paths.run_dir.name


def _read_metrics(paths: RunPaths) -> dict:
    """metrics.json of THIS run, in the current schema."""
    _require(paths, METRICS)
    metrics = _read_json(paths.out(METRICS))
    if metrics.get("schema_version") != train.SCHEMA_VERSION:
        raise ToolRefused("metrics.json has an unsupported schema version; run training again")
    if metrics.get("run_id") != _run_id(paths):
        raise ToolRefused("metrics.json belongs to another run; it must not be used here")
    return metrics


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class _Ml(_RunTool):
    """Base: clears downstream stale files first and cleans up after a failure."""

    produces: tuple[str, ...] = ()  # outputs of this tool; also everything downstream of them
    # (class-level lists are overridden in subclasses)

    def _run(self, **kwargs: Any) -> str:
        clear_outputs(self.paths, self.produces)
        try:
            return self._work(**kwargs)
        except ToolRefused as exc:
            clear_outputs(self.paths, self.produces)
            logger.warning("%s refused in run %s: %s", self.name, _run_id(self.paths), exc)
            raise
        except DOMAIN_ERRORS as exc:
            clear_outputs(self.paths, self.produces)
            logger.warning(
                "%s failed in run %s: %s: %s",
                self.name,
                _run_id(self.paths),
                type(exc).__name__,
                exc,
            )
            raise ToolRefused(f"{type(exc).__name__}: {exc}") from exc

    def _work(self, **kwargs: Any) -> str:
        raise NotImplementedError


# ------------------------------------------------------------------- Agent 4


class BuildFeaturesTool(_Ml):
    name: str = "build_features"
    description: str = (
        "Re-check the clean data against the dataset contract, then build features.csv (lags "
        "of 28 days or more, rolling statistics, calendar, event, SNAP and closure features) "
        "for the observed days and the 28 future days, and validate it. Takes no input. "
        "Returns counts and the feature list, never data rows."
    )
    produces: tuple[str, ...] = tuple(CREW2_OUTPUTS)

    def _work(self, **_: Any) -> str:
        _require(self.paths, CLEAN_DATA, CONTRACT, CONTRACT_CHECK)
        if _read_json(self.paths.out(CONTRACT_CHECK))["status"] != contract.PASS:
            raise ToolRefused("Gate 1 did not pass; features must not be built.")
        scope = load_scope(self.paths.scope_path)
        clean_df = pd.read_csv(self.paths.out(CLEAN_DATA))
        report = contract.contract_report(
            contract.check_against_contract(
                clean_df, contract.load_contract(self.paths.out(CONTRACT))
            )
        )
        contract.write_json(report, self.paths.out(CONTRACT_RECHECK))
        if report["status"] != contract.PASS:
            raise ToolRefused(
                f"The clean data no longer matches the contract: {report['failed_rules']}"
            )
        clean = ft.load_clean(self.paths.out(CLEAN_DATA))
        calendar = ft.load_calendar(
            self.paths.raw_dir / "calendar.csv", str(clean["state_id"].iloc[0])
        )
        table = ft.build_features(clean, calendar, scope)
        ft.write_features(table, self.paths.run_dir)
        observed = table[spec.TARGET_COLUMN].notna()
        return _json(
            {
                "contract_recheck": report["status"],
                "rows": len(table),
                "observed_rows": int(observed.sum()),
                "future_rows": int((~observed).sum()),
                "items": table["item_id"].nunique(),
                "required_features": spec.FEATURE_COLUMNS,
                "numeric_features": spec.NUMERIC_FEATURES,
                "categorical_features": spec.CATEGORICAL_FEATURES,
                "minimum_lookback_days": spec.MIN_LOOKBACK_DAYS,
                "longest_lookback_days": spec.longest_lookback(),
                "price_feature_used": False,
                "all_28_day_windows_complete": True,  # validate_features raised otherwise
                "rows_with_incomplete_history": int(
                    table[spec.FEATURE_COLUMNS].isna().any(axis=1).sum()
                ),
            }
        )


# ------------------------------------------------------------------- Agent 5


class TrainModelsTool(_Ml):
    name: str = "train_models"
    description: str = (
        "Tune Ridge and Random Forest on the three backtest windows, select the model by the "
        "fixed rule, score it once on the test window, refit on all history and write the "
        "model, metrics and both forecasts. Takes no input: the grids, the selection rule and "
        "the seed are fixed in code and cannot be changed. Returns the tuning summary."
    )
    produces: tuple[str, ...] = (*TRAIN_OUTPUTS, *REPORT_OUTPUTS)

    def _work(self, **_: Any) -> str:
        _require(self.paths, FEATURES, CONTRACT_RECHECK, CLEAN_DATA)
        if _read_json(self.paths.out(CONTRACT_RECHECK))["status"] != contract.PASS:
            raise ToolRefused("The contract re-check did not pass; models must not be trained.")
        scope = load_scope(self.paths.scope_path)
        features = ft.read_features(self.paths.out(FEATURES))
        clean = baseline_eval.load_clean_data(self.paths.out(CLEAN_DATA))
        metrics, test_forecast, forecast, bundle = train.run(
            features, clean, scope, _run_id(self.paths)
        )
        train.write_outputs(metrics, test_forecast, forecast, bundle, self.paths.run_dir)
        selection = metrics["selection"]
        return _json(
            {
                "selected_model": metrics["selected_model"],
                "selected_hyperparameters": selection["selected_hyperparameters"],
                "selection_metric": selection["metric"],
                "selection_data": selection["data"],
                "grids": selection["grids"],
                "n_candidates": selection["n_candidates"],
                "mean_backtest": {
                    m: metrics["models"][m]["backtest"]["mean_overall"] for m in metrics["models"]
                },
                "beats_baseline_on_backtest": selection["beats_baseline_on_backtest"],
                "refit_fitted_through_day": metrics["refit"]["fitted_through_day"],
                "model_version": metrics["refit"]["model_version"],
                "files": TRAIN_OUTPUTS,
            }
        )


# ------------------------------------------------------------------- Agent 6


class GetEvaluationFactsTool(_RunTool):
    name: str = "get_evaluation_facts"
    description: str = (
        "Return the numbered evaluation facts (backtest, final test and per demand group "
        "scores) from this run's metrics.json. Takes no input. Each fact has an id, a "
        "'display' text, a unit and labels (model, metric, period, group). Write a number "
        "only as a fact's exact display text followed by its id."
    )

    def _run(self, **_: Any) -> str:
        metrics = _read_metrics(self.paths)
        facts = evaluation_text.build_facts(metrics)
        shown = [{**f, "display": fmt(f["value"], f["unit"])} for f in facts]
        self.paths.out(EVALUATION_FACTS).write_text(json.dumps(shown, indent=2), "utf-8")
        return _json(
            {
                "selected_model": metrics["selected_model"],
                "selection_is_fixed": "computed by Python; it cannot be changed or contested",
                "periods": {
                    "backtest": "model comparison and tuning only",
                    "test": "final evaluation, scored once, model fitted before the test window",
                    "refit": "model refitted on all history for the future forecast; not scored",
                },
                "facts": [
                    {k: f[k] for k in ("id", "display", "unit", "labels", "definition")}
                    for f in shown
                ],
            }
        )


class SaveNarrativeInput(BaseModel):
    """Input of save_evaluation_narrative."""

    summary: str = Field(..., description="Short summary paragraph in Markdown")
    interpretation: str = Field(..., description="Interpretation section in Markdown")


class SaveEvaluationNarrativeTool(_RunTool):
    """Checks the narrative and, if it passes, writes evaluation_report.md and model_card.md.

    Every attempt is recorded in evaluation_attempts.json. Both files are written, with all
    tables and technical sections rendered by Python, or neither.
    """

    name: str = "save_evaluation_narrative"
    description: str = (
        "Save the narrative of the evaluation report and model card: a short 'summary' and an "
        "'interpretation'. Every number must be a fact's exact display text followed by its "
        "id, after naming that fact's model, metric and period in the same sentence, for "
        "example 'Ridge has a test MAE of 1.35 [F10] units per item-day'. Dates, hyperparameters "
        "and tables are written by Python. No causal explanations, no claims that a model was "
        f"selected other than the fixed selection. At most {MAX_SAVE_ATTEMPTS} attempts. "
        "Returns 'saved' or the problems to fix."
    )
    args_schema: type[BaseModel] = SaveNarrativeInput

    def _run(self, summary: str, interpretation: str, **_: Any) -> str:
        clear_outputs(self.paths, [EVALUATION_REPORT, MODEL_CARD])  # only a pass leaves them
        metrics = _read_metrics(self.paths)
        attempts = read_evaluation_attempts(self.paths)
        if len(attempts) >= MAX_SAVE_ATTEMPTS:
            return _json(
                {
                    "saved": False,
                    "attempts_left": 0,
                    "message": "No attempts left. Give your final answer; the deterministic "
                    "template narrative will be used.",
                }
            )
        problems = [
            *(f"summary: {p}" for p in evaluation_text.check_evaluation_text(summary, metrics)),
            *(
                f"interpretation: {p}"
                for p in evaluation_text.check_evaluation_text(interpretation, metrics)
            ),
        ]
        attempts.append({"attempt": len(attempts) + 1, "saved": not problems, "problems": problems})
        self.paths.out(EVALUATION_ATTEMPTS).write_text(json.dumps(attempts, indent=2), "utf-8")
        if not problems:
            write_reports(self.paths, metrics, reports.Narrative(summary, interpretation), "agent")
            return _json({"saved": True})
        left = MAX_SAVE_ATTEMPTS - len(attempts)
        return _json(
            {
                "saved": False,
                "problem_count": len(problems),
                "problems": problems[:MAX_PROBLEMS_SHOWN],
                "more_problems_not_shown": max(0, len(problems) - MAX_PROBLEMS_SHOWN),
                "attempts_left": left,
                "hint": "Fix these and similar problems in both texts, then call "
                "save_evaluation_narrative again with the full texts."
                if left
                else "No attempts left; give your final answer.",
            }
        )


def read_evaluation_attempts(paths: RunPaths) -> list[dict]:
    """The save_evaluation_narrative attempts of this run ([] before the first one)."""
    path = paths.out(EVALUATION_ATTEMPTS)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def write_reports(
    paths: RunPaths,
    metrics: dict,
    narrative: reports.Narrative,
    source: str,
    reason: str | None = None,
) -> None:
    """Render and write evaluation_report.md and model_card.md together (both or neither)."""
    texts = {
        EVALUATION_REPORT: reports.render_evaluation_report(metrics, narrative, source, reason),
        MODEL_CARD: reports.render_model_card(metrics, narrative, source, reason),
    }
    try:
        for name, text in texts.items():
            paths.out(f"{name}.tmp").write_text(text, encoding="utf-8")
        for name in texts:
            os.replace(paths.out(f"{name}.tmp"), paths.out(name))
    except OSError:
        clear_outputs(paths, [EVALUATION_REPORT, MODEL_CARD])
        raise


def write_template_reports(paths: RunPaths, reason: str) -> None:
    """Fallback for the runner: both files with the deterministic template narrative."""
    metrics = _read_metrics(paths)
    write_reports(paths, metrics, reports.template_narrative(metrics), "template", reason)


def feature_tools(paths: RunPaths) -> list[BaseTool]:
    """Tools of Agent 4, the Feature Engineer."""
    return [BuildFeaturesTool(paths=paths)]


def trainer_tools(paths: RunPaths) -> list[BaseTool]:
    """Tools of Agent 5, the Model Trainer."""
    return [TrainModelsTool(paths=paths)]


def evaluator_tools(paths: RunPaths) -> list[BaseTool]:
    """Tools of Agent 6, the Model Evaluator."""
    return [GetEvaluationFactsTool(paths=paths), SaveEvaluationNarrativeTool(paths=paths)]
