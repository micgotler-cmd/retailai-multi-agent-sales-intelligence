# Agents and Tasks

Who does what, and what passes between them. Flow and gates: [architecture.md](architecture.md). Requirements: M-01 to M-06 in [project-specification.md](project-specification.md).

Rule for every agent: **tools do the computation; the agent decides which tool to call, interprets results and writes the explanation.** Tools are plain tested Python functions (see [architecture.md](architecture.md); location of tool wrappers is TBD, T-20).

## Agent overview

| # | Agent | Crew | Inputs | Outputs | Tools (deterministic) |
|---|---|---|---|---|---|
| 1 | Data Validator | Crew 1 | Raw M5 CSVs | `quality_report.json` | Schema, null, duplicate, date-gap, range checks |
| 2 | Data Cleaner | Crew 1 | Raw CSVs + quality report | `clean_data.csv`, cleaning log | Wide-to-long ETL, calendar/price joins, filtering to the item subset |
| 3 | Business Analyst | Crew 1 | `clean_data.csv` | `eda_report.html`, `insights.md`, `dataset_contract.json` | Matplotlib/Seaborn charts, summary statistics, contract writer |
| 4 | Feature Engineer | Crew 2 | `clean_data.csv` + contract | `features.csv` | Calendar, lag, rolling features with leakage checks |
| 5 | Model Trainer | Crew 2 | `features.csv` | `model.joblib` (both variants) | Chronological split, fit Ridge and Random Forest, seeds |
| 6 | Model Evaluator | Crew 2 | Models + test data | `evaluation_report.md`, `model_card.md`, forecast table | Seasonal Naive, MAE/RMSE overall and per item |
| 7 | Business Recommendation Agent | Independent | `insights.md`, validated forecast summary, retrieved policy excerpts | `recommendation.json` | Retriever, citation verifier |

Agents 1-6 are mandatory (M-01). Agent 7 is an optional, time-boxed enhancement (O-01, D-16).

## Crew 1: Data Analyst (M-02, M-03)

| Task | Owner agent | Done when |
|---|---|---|
| Validate raw files | Data Validator | `quality_report.json` lists schema, missing-value, duplicate and anomaly findings; blocking issues are flagged |
| Clean and document | Data Cleaner | `clean_data.csv` saved; every cleaning action recorded; missing prices examined, not silently imputed (T-13) |
| EDA and insights | Business Analyst | `eda_report.html` with charts; `insights.md` with findings; sales by store/department/time |
| Dataset contract | Business Analyst | `dataset_contract.json` holds types, keys, ranges, allowed values, missing-value policy, assumptions, constraints, schema version, source (M-24, T-12) |

Crew 1 ends at Gate 1 (contract matches clean data). Crew 2 must not start if it fails.

**Implementation (P-04):** agents in `src/agents/data_analyst_agents.py`, tasks and crew in `src/crews/data_analyst_crew.py`, tools in `src/tools/data_tools.py` (T-20). Each agent has only its own tools: Data Validator `validate_raw_data`; Data Cleaner `build_clean_data`; Business Analyst `run_eda`, `write_dataset_contract`, `save_insights`. Tools are bound to one run folder `artifacts/runs/<run_id>/`, so agents never choose file paths, and they return JSON summaries only (no data rows to the LLM, T-04). A tool refuses to run when its prerequisite is missing or failed (for example cleaning after a failed validation). `save_insights` accepts the insights only if every number is a fact's display value followed by its id (`src/data/insights_check.py`; a citation after a word, with no number, is accepted as a reference); otherwise the runner keeps the deterministic template insights and records it. After the crew, the runner checks the outputs itself and writes `crew1_report.json` (status, problems, insights source, LLM calls and tokens). Agents run without delegation and with capped iterations (4, Business Analyst 7). The per-run call and token caps (`LLM_MAX_CALLS_PER_RUN`, `LLM_MAX_TOKENS_PER_RUN`) are required arguments of the runner and are enforced for every LLM call; calls and tokens used are saved in `crew1_report.json` (`llm_budget`).

## Crew 2: Data Scientist (M-04, M-05, M-06)

| Task | Owner agent | Done when |
|---|---|---|
| Validate inputs, build features | Feature Engineer | Contract re-checked against `clean_data.csv`; `features.csv` saved; every required feature exists; no feature uses data that is unavailable at forecast time |
| Train two variants | Model Trainer | Both variants fit on training data only; `model.joblib` saved; seeds recorded |
| Evaluate and document | Model Evaluator | Seasonal Naive, Ridge, Random Forest compared on the same 28-day holdout by MAE and RMSE (overall and per item); `evaluation_report.md` and `model_card.md` saved (purpose, training data summary, metrics, limitations, ethical considerations) |

Crew 2 ends at Gate 2 (forecast valid). Method details: [data-and-ml.md](data-and-ml.md).

## Agent 7: Business Recommendation Agent (O-01)

Runs once, after Gate 2. Does not rerun the Business Analyst. Full design: [rag-and-recommendations.md](rag-and-recommendations.md).

| Aspect | Rule |
|---|---|
| Input | `insights.md`, a structured forecast summary (item, store, horizon, predicted units, trend, error metrics, `run_id`), retrieved policy excerpts with `source_id` |
| Output | `recommendation.json` with the fields listed in [rag-and-recommendations.md](rag-and-recommendations.md) |
| May | Retrieve policy, quote it, propose a recommendation for human review, state uncertainty, abstain |
| Must not | Train or retrain models, modify sales data, activate promotions, fabricate policies or citations, give unsupported numeric discount advice, claim causal effects |
| Failure | Retrieval error or no applicable source gives `insufficient_evidence` or `unavailable`; the forecast stays valid and visible |

## Handoff contracts

| From | To | Contract |
|---|---|---|
| Crew 1 | Crew 2 | Four artifacts plus `dataset_contract.json`; Gate 1 verifies the contract against `clean_data.csv` |
| Crew 2 | Flow | Model, features, metrics, forecast table; Gate 2 verifies features, horizon and holdout metrics |
| Flow | Agent 7 | Forecast summary JSON tied to a `run_id` and read-only access to `insights.md`; no write access to data or models |
| Agent 7 | Flow | `recommendation.json`; validated by the citation checks before it is stored |

Contract file format: versioned JSON (T-12, Approved; see [data-and-ml.md](data-and-ml.md)). Which item(s) get a recommendation: TBD (T-14).

## Ownership (spec s15, T-11 structure Approved)

Developer A is Lilach, Developer B is Michal (T-11, confirmed 2026-11-18); [progress.md](progress.md) shows roles (Dev A, Dev B, Shared).

| Area | Developer A | Developer B | Shared |
|---|---|---|---|
| Data | M5 ingestion and preprocessing, validation and cleaning, EDA, dataset contract | | |
| Crews | Data Analyst Crew (3 agents) | Data Scientist Crew (3 agents) | |
| ML | | Feature engineering, model training and evaluation, 28-day product-level forecasting | |
| UI | Data Streamlit screens (Home, Data Quality, EDA, Insights) | Forecasting screens (Forecast, Model Evaluation) | Run History |
| Integration | | | CrewAI Flow orchestration and integration, end-to-end testing |
| Extensions | | | Agent 7, RAG, Supabase |
| Delivery | | | Final presentation and demo |

## Interfaces between workstreams (Proposed)

To allow parallel work, each handoff has an agreed file format. These are frozen at the end of week 1; changing one needs a PR that updates this table, the producer and the consumer's tests.

| Interface | From | To | Content |
|---|---|---|---|
| `clean_data.csv` | A | B, Flow | Columns as in the contract: the spec s5 fields plus `store_closed` (0/1, T-13); one row per `date` x `store_id` x `item_id` from each item's first sale to d_1941, no gaps; sorted by `item_id`, `date`; no future dates; no missing `sell_price` |
| `dataset_contract.json` | A | B, Flow | See [data-and-ml.md](data-and-ml.md) |
| `quality_report.json` | A | UI | List of checks with status and message |
| Test fixture | A | A, B, Flow | Small synthetic M5-shaped dataset under `tests/` (not real M5 rows) |
| `features.csv` | B | B, Flow | Keys, target and feature columns; list of required features recorded for Gate 2 |
| `forecast.csv` | B | Flow, UI, Repository | `run_id`, `store_id`, `item_id`, `forecast_date`, `predicted_units`, `model_version` (matches [database-design.md](database-design.md)) |
| `metrics.json` | B | Flow, UI, Agent 7 | MAE and RMSE overall and per item for the baseline and both models; split boundaries |
| Forecast summary JSON | Flow | Agent 7 | As in the handoff table above |
| Repository interface | Shared | All | See [database-design.md](database-design.md) |

## LLM usage

All seven agents use OpenAI models through shared configuration; limits and cost controls are in [architecture.md](architecture.md) (T-01). Week-by-week plan: [implementation-plan.md](implementation-plan.md).
