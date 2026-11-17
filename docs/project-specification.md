# RetailAI: Project Specification (Markdown)

Source of truth for requirements. Converted from [RetailAI_Project_Specification.docx](RetailAI_Project_Specification.docx) (v1.3, November 2026), which stays in this folder for reference. The instructor brief ([final_project_brief_1.html](final_project_brief_1.html)) is binding for the mandatory academic requirements.

Other documents link to the requirement IDs below instead of repeating them. Decisions and open items live in [decisions.md](decisions.md).

**Legend**

| Tag | Meaning |
|---|---|
| **Mandatory (Brief)** | Required by the instructor brief |
| **Mandatory (MVP)** | Required by the team spec for the MVP |
| **Optional** | Time-permitting enhancement, never allowed to endanger mandatory items |

## 1. Executive Summary

RetailAI analyzes retail sales, produces business insights, and forecasts product-level demand. It uses two required CrewAI crews of three agents each, plus an independent seventh Business Recommendation Agent (RAG-powered decision support) triggered only after forecasting. RAG and Supabase remain time-boxed planned enhancements.

## 2. Business Problem and Objectives

- Businesses need to detect sales trends and anticipated downturns in time.
- Historical analysis alone is insufficient for inventory and commercial planning.
- The system produces data reports, model-based forecasts, and model performance comparisons.
- Desirable extension: identify weak periods and examine associations between promotions and sales, without claiming causation (see O-03, O-07).

## 3. Project Scope and MVP Boundaries

### Mandatory requirements

| ID | Requirement | Tag |
|---|---|---|
| M-01 | Two CrewAI crews with at least 3 agents each (this project: exactly 3 + 3) | Mandatory (Brief) |
| M-02 | Crew 1 (Data Analyst) outputs: `clean_data.csv`, `eda_report.html`, `insights.md`, `dataset_contract.json` | Mandatory (Brief) |
| M-03 | Crew 1 responsibilities: ingest and validate a dataset, clean/preprocess/document it, descriptive analytics and EDA, visual insights and business summaries, define the dataset contract | Mandatory (Brief) |
| M-04 | Crew 2 (Data Scientist) outputs: `features.csv`, `model.pkl` or `model.joblib`, `evaluation_report.md`, `model_card.md` | Mandatory (Brief) |
| M-05 | Crew 2 responsibilities: read/validate the cleaned dataset and contract, feature engineering, train at least one predictive model, compare at least 2 model variations | Mandatory (Brief) |
| M-06 | Model card covers purpose, training data summary, metrics, limitations, ethical considerations | Mandatory (Brief) |
| M-07 | A CrewAI Flow automates the handoff Crew 1 to Crew 2 | Mandatory (Brief) |
| M-08 | Flow validations: contract matches the cleaned dataset; all required features exist before modeling | Mandatory (Brief) |
| M-09 | Reproducibility: deterministic steps, clear logging, artifacts saved inside the repo | Mandatory (Brief) |
| M-10 | Flow fails gracefully when validations break | Mandatory (Brief) |
| M-11 | Stack: CrewAI, Python, Pandas, Scikit-Learn, Matplotlib/Seaborn | Mandatory (Brief) |
| M-12 | Git + GitHub with Pull Requests; a documented PR from each developer | Mandatory (Brief / Spec s13) |
| M-13 | Streamlit or Flask UI (frontend may use HTML + CSS) | Mandatory (Brief) |
| M-14 | Deliverables: repository (code, artifacts, docs), business presentation of 10-12 slides, demo video of at most 5 minutes | Mandatory (Brief) |
| M-15 | README with setup, commands, inputs/outputs, limitations (reproducible by others) | Mandatory (Spec s12/s13) |
| M-16 | MVP forecast target: daily units sold for the next 28 days per `item_id` x `store_id`; Seasonal Naive baseline plus two Scikit-Learn variations (for example Ridge and Random Forest); MAE and RMSE overall and per item on the same test horizon | Mandatory (MVP) |
| M-17 | Chronological train/validation/test split, final holdout of at least 28 days, no random shuffling; leakage prevention (section 8) | Mandatory (MVP) |
| M-18 | Initial scope: one store and 20-50 selected items | Mandatory (MVP) |
| M-19 | A schema validation failure stops the Flow before training with a clear error | Mandatory (MVP) |
| M-20 | Pin seeds, dependencies, dataset version and run identifier; document split boundaries and assumptions | Mandatory (MVP) |
| M-21 | API keys only in `.env` (excluded from Git); LLM-generated code is not executed without review | Mandatory (MVP) |
| M-22 | Use a defined development subset and limit LLM calls | Mandatory (MVP) |
| M-23 | Streamlit screens: Home, Data Quality, Business Insights, Forecast & Evaluation, Run History / Logs | Mandatory (MVP) |
| M-24 | Dataset contract specifies types, keys, ranges, missing-value policy, schema version, source (plus allowed values, assumptions, constraints per the brief) | Mandatory (Brief / MVP) |

### Time-permitting extensions

| ID | Requirement | Tag |
|---|---|---|
| O-01 | Agent 7, Business Recommendation Agent with RAG (section 10); `recommendation.json` | Optional (time-boxed) |
| O-02 | Supabase persistence (section 10A); app must work without it | Optional |
| O-03 | Promotions module: descriptive price vs units analysis only (section 9) | Optional |
| O-04 | Discount simulator, only with real price/discount data | Optional |
| O-05 | Cloud deployment (Streamlit Cloud, Railway) | Optional |
| O-06 | Streamlit "Recommendations" screen (if Agent 7 exists) | Optional |
| O-07 | Flag weak periods in the sales data | Optional |

### Out of scope

A live coupon engine, automatic promotion activation, payment systems, user authentication/authorization, and profit forecasts without cost data.

## 4. Users and Use Cases

- Analyst/business manager: select or upload a supported dataset and run the pipeline.
- Business user: explore sales by store, product family (in M5: `dept_id` / `cat_id`), and time period.
- Business user: inspect forecasts and compare two models.
- Business user: see flagged weak periods and a qualified suggestion to consider a promotion, where supported by the data (O-01, O-07).

## 5. Dataset Selection and Data Contract

Selected planning dataset: Kaggle M5 Forecasting - Accuracy (Walmart), pending download, usage-rights review, data inspection, and a baseline proof of concept. Observation grain: date x store x item (`item_id`). Initial scope per M-18. Details of the approach: [data-and-ml.md](data-and-ml.md).

| Field | Meaning / validation |
|---|---|
| `date` | Date mapped via `calendar.csv` |
| `store_id` | Non-null store identifier |
| `item_id` | Non-null product identifier |
| `units_sold` | Nonnegative daily unit count |
| `sell_price` | Positive weekly price when present; documented null policy |
| `wm_yr_wk` | Week key for price/calendar join |

Source files: `sales_train_validation.csv` (daily unit sales in wide `d_1`, `d_2`, ... columns), `calendar.csv` (day/date, `wm_yr_wk`, events), `sell_prices.csv` (weekly price by `store_id`, `item_id`, `wm_yr_wk`). ETL reshapes sales into long form and joins calendar and prices on the documented keys.

Planned normalized fields: `date, store_id, item_id, dept_id, cat_id, state_id, units_sold, sell_price, wm_yr_wk, event_name_1, event_type_1`, and a state-specific SNAP indicator. Missing prices must be examined rather than silently imputed. `dataset_contract.json` specifies types, keys, ranges, missing-value policy, schema version, and source (M-24).

M5 provides no explicit coupon, promotion flag, or discount-percentage field. A price change is not necessarily a promotion. The MVP does not claim causal discount effects or reliable coupon-response predictions.

## 6. Architecture and End-to-End Workflow

Source CSV, then Data Analyst Crew (3 agents) producing `clean_data.csv`, EDA, insights and `dataset_contract.json`, then a Validation Gate, then Data Scientist Crew (3 agents) producing features, models and forecast, then a Forecast Validation Gate, then the Business Recommendation Agent (Agent 7, RAG) producing `recommendation.json`, then Streamlit / Supabase (when enabled).

The CrewAI Flow coordinates both crews, validates contracts and forecast outputs, then invokes Agent 7 as an independent post-forecast task. A retrieval failure must not invalidate a successful forecast: the recommendation stage abstains, logs the issue, and preserves the forecast for display. Diagram and state model: [architecture.md](architecture.md).

## 7. Agent Specifications

| Crew / Agent | Input | Responsibility and output |
|---|---|---|
| Analyst: Data Validator | Raw CSV | Check schemas, missing values, duplicates, anomalies; quality report |
| Analyst: Data Cleaner | CSV + quality report | Documented cleaning; save `clean_data.csv` |
| Analyst: Business Analyst | Cleaned data | EDA, charts, `insights.md`, `dataset_contract.json` |
| Scientist: Feature Engineer | Clean data + contract | Leak-free features; `features.csv` |
| Scientist: Model Trainer | Features | Train and persist two model variants |
| Scientist: Model Evaluator | Models + test data | Compare metrics; `evaluation_report.md`, `model_card.md` |
| Independent: Agent 7 (RAG) | `insights.md` + validated forecast + retrieved policy | `recommendation.json` + evidence |

Detailed responsibilities, tools and handoffs: [agents-and-tasks.md](agents-and-tasks.md).

## 8. Forecasting Model and Evaluation

- MVP target: M-16. Limit the initial implementation and demo to one store and 20-50 items, depending on history coverage and compute (M-18).
- Candidate features: day of week, month, known future calendar events, 7/14/28-day sales lags, past-only rolling statistics, and prices only when available at prediction time. Multi-step forecasting must use recursive predicted lags or another leakage-safe horizon strategy.
- Compare a Seasonal Naive baseline with two Scikit-Learn model variations. Chronological splits, final holdout of at least 28 days; report MAE and RMSE for the same test horizon, overall and by item.
- Prevent leakage: exclude target-day observations from rolling features, do not assume unknown future prices, never use test observations for training or tuning. Document seeds, library versions, split boundaries, and assumptions (M-20).
- Required artifacts: `features.csv`, `model.pkl` or `model.joblib`, `evaluation_report.md`, `model_card.md`. Include limitations for intermittent-demand items and the absence of inventory data.

## 9. Promotions Module (Controlled Extension, O-03)

Secondary extension only: descriptive analysis of weekly `sell_price` changes versus `units_sold` by item and store, accounting for seasonality and known events. M5 has no explicit promotion/coupon labels; do not label every price change as a promotion or infer causal lift.

When forecast demand declines, Agent 7 may suggest considering a promotion only when supported by a validated forecast and retrieved policy, with explicit evidence and limitations. It must not retrain models, change data, activate promotions, or claim a causal lift.

## 10. Business Knowledge and RAG Integration (O-01)

**Purpose:** a small but meaningful RAG integration lets the independent Agent 7 combine validated forecasts, historical insights, and business policy excerpts into qualified, source-grounded recommendations.

**Knowledge sources (initial version)**
- 3-5 short local Markdown or PDF documents: sample promotion policy, discount limits, inventory/seasonality rules, recommendation-writing guidelines. The generated `insights.md` may also be included, but distinguish source data from LLM-generated material.
- Each document records `source_id`, title, date/version, owner, source type, and path. Synthetic demo policies must be explicitly labeled as synthetic and never represented as a real retailer's policy.

**Ingestion, indexing, retrieval**
- MVP: CrewAI built-in Knowledge/retrieval, subject to compatibility checks for the installed version; alternatively a small local Chroma store. No Supabase, hosted vector database, or fully custom RAG framework is necessary.
- Pipeline: load documents, chunk, create embeddings and an index, semantic search for the agent's question, pass 2-4 relevant excerpts with source identifiers. Configure the embedding model separately; never hard-code API keys.
- Keep deterministic numeric computation (Pandas/Scikit-Learn) separate from policy-text retrieval. RAG is not a forecasting model and must not replace the dataset.

**Integration with Agent 7**
- Independent of the two crews (3+3); runs once after the Forecast Validation Gate; does not require re-running the historical Business Analyst.
- The Flow passes Agent 7 a structured summary (item, store, horizon, predicted units, trend, error metrics, run ID). Agent 7 retrieves relevant product/category policy constraints and generates one qualified recommendation.
- Output `recommendation.json`: `recommendation`, `rationale`, `evidence [{source_id, section, quote_or_excerpt}]`, `forecast_reference`, `limitations`, `confidence_note`, `recommendation_status`. Without an applicable source: "No supporting policy found"; never fabricate citations or numeric discount advice.
- Example: "Demand for product family X is forecast to decline next month; under section 2 of synthetic demo policy PROMO_POLICY_v1, a promotion may be considered subject to profitability review." This is a proposal for review, not a causal claim.

**RAG tests and acceptance**
- Test set of 8-12 questions with expected sources: policy section retrieval, no-source case, conflicting/outdated policy, irrelevant document, prompt-injection attempt embedded in a document.
- Automated checks: `forecast_reference` matches a validated run; every `source_id` exists; quoted excerpts occur in their source; no unsupported numeric discount advice; Agent 7 does not train models or modify data. Without evidence, `recommendation_status = insufficient_evidence`.
- Acceptance: at least 8 of 10 test questions receive a correct source or correct abstention; zero fabricated references in the test sample. Retrieval failure must not stop forecasting; show "Knowledge-grounded recommendation unavailable."

**Time constraint:** approximately 4-6 hours for basic RAG plus a bounded allowance for Agent 7 wiring and tests. If it threatens the deadline, isolate or defer recommendations; the mandatory Flow and forecasts must still work. Design: [rag-and-recommendations.md](rag-and-recommendations.md).

## 10A. Supabase Integration (O-02, planned, Should Have)

Not an instructor-mandated requirement. Design for Supabase from day one, but connect it only after the local pipeline works. The application must remain functional without cloud access.

- **Purpose:** persist run history, sales predictions, and business insights; display prior results in Streamlit. No need to migrate the entire sales dataset or implement user authentication.
- **Architecture:** a separate Data Access / Repository layer with stable interface (`save_run`, `save_predictions`, `save_insights`, `list_runs`, `get_run`). `LocalRepository` first, then `SupabaseRepository`. Backend chosen by environment configuration. Crews and ML code must not call Supabase directly.
- **Schema:** see [Corrections](#corrections-to-the-original-word-spec) below and [database-design.md](database-design.md).
- **Artifacts:** the eight mandatory files remain saved locally in the repository deliverables. Optional Supabase Storage copies or links must not replace required outputs.
- **RAG:** CrewAI Knowledge or local vector store initially. pgvector is not required.
- **Security and operations:** credentials in `.env` or deployment secrets, never in Git. Do not expose a `service_role` key to client-side code; least-privilege access and RLS as appropriate. If Supabase is unavailable, show a clear error and preserve local outputs per the configured fallback policy.
- **Acceptance tests:** (1) full pipeline with LocalRepository only; (2) read/write run, prediction and insight records in Supabase; (3) consistent behavior across backends; (4) retry does not duplicate records; (5) unavailable Supabase does not compromise mandatory artifacts; (6) no secrets in source code or logs.
- **Schedule:** week 1 interface, schema, LocalRepository; week 2 crews and local ML; week 3 Supabase project, migrations, adapter, Streamlit integration; week 4 integration tests, fixes, submission. If delayed, defer Supabase connectivity.

## 11. Streamlit UI Specification (M-13, M-23, O-06)

- Home: system overview, supported dataset selection, pipeline execution, status.
- Data Quality: field summary, missing values, cleaning actions, validation results.
- Business Insights: charts, trends by store/product family, business findings.
- Forecast & Evaluation: series selection, forecast, MAE/RMSE, model comparison.
- Run History / Logs: run status, errors, links to artifacts.
- Recommendations (if Agent 7 is implemented): grounded recommendation, evidence, forecast reference, limitations, abstention status. No causal claim or numeric discount without appropriate data.

Screen-level design: [architecture.md](architecture.md).

## 12. Non-Functional Requirements

- Reliability: schema validation failure stops the Flow before training and produces a clear error (M-19).
- Reproducibility: pin seeds, dependencies, dataset version, run identifier (M-20).
- Security: API keys in a `.env` excluded from Git; do not execute LLM-generated code without review (M-21).
- Performance and cost: defined development subset; limit LLM calls (M-22).
- Documentation: README with setup, commands, inputs/outputs, limitations (M-15).

## 13. System Tests and Acceptance

| Scenario | Acceptance criterion |
|---|---|
| Valid CSV | All eight mandatory artifacts are generated |
| Missing required field | Readable error; Crew 2 does not start |
| Invalid contract value | Controlled validation failure; logged |
| Model evaluation | Metrics computed on held-out chronological test data |
| Repeated execution | Deterministic steps produce reproducible results |
| RAG retrieval failure | Forecast still works; grounded recommendation unavailable |
| GitHub | A documented PR from each developer exists, and the README allows reproduction |
| Agent 7 has no supporting policy | No fabricated citations; `insufficient_evidence`; forecast remains available |

Test plan: [testing-strategy.md](testing-strategy.md).

## 14. Proposed Repository Structure

```
retailai/  app/streamlit_app.py  src/crews/analyst/  src/crews/scientist/  src/flow/
           src/tools/  src/ml/  data/raw/  data/processed/  artifacts/  tests/  docs/
           requirements.txt  README.md  .env.example
```

A more detailed proposal is in [architecture.md](architecture.md) (status: Proposed, see [decisions.md](decisions.md)).

## 15. Ownership and Git Workflow

Developer A leads the Analyst Crew and data views; Developer B leads the Scientist Crew and forecasting views. Both define the Agent 7 handoff contract, citation checks, and Flow integration. Supabase remains a planned enhancement. Plan: [implementation-plan.md](implementation-plan.md).

## 16. Four-Week Schedule

| Week | Tasks | Exit criterion |
|---|---|---|
| 1 | Dataset, initial contract, repository, Pandas/ML PoC; begin Analyst Crew | Clean data and working baseline |
| 2 | Finish both crews, two models, artifacts | Each crew works independently |
| 3 | CrewAI Flow, validation, Streamlit, integration tests; Agent 7 only after forecast validation; Supabase as time permits | End-to-end execution |
| 4 | QA, optional RAG timebox, documentation, slides, demo | Stable submission package |

## 17. Risks and Open Decisions

- Dataset: M5 is the planning choice, subject to file inspection, quality and usage-rights checks.
- Scope: start with one store and 20-50 items; inspect sparsity, missing dates and wide-to-long ETL cost.
- 28-day horizon: only use features genuinely available when the forecast is generated.
- No explicit coupon/promotion fields: recommendations must be policy-grounded, not causal claims.
- Prioritize the required Flow and artifacts before RAG and Supabase extensions.
- Supabase stays a planned integration (Should Have): design the data access layer in week 1, connect in week 3 after the local MVP.
- Confirm whether the instructor needs separate approval for extensions; preserve the original Flow requirements.

All open items are tracked in [decisions.md](decisions.md).

## 18. Submission Deliverables (M-14)

Analyst artifacts: `clean_data.csv`, `eda_report.html`, `insights.md`, `dataset_contract.json`. Scientist artifacts: `features.csv`, `model.pkl` or `model.joblib`, `evaluation_report.md`, `model_card.md`. Additionally: source repository and documentation, a 10-12 slide business presentation, and a demo video of at most 5 minutes.

## 19. Sources and Requirement Status

Binding source: `final_project_brief_1.html` (Industry-Simulated AI Product Workflow). Supplementary source named in the Word spec: `RetailAI - Multi-Agent Sales Intelligence.pdf` (not in this repository, not reviewed). M5, promotion analytics, and RAG are proposed enhancements, not mandatory requirements.

## Brief compliance summary

| Brief item | Requirement IDs |
|---|---|
| Crew 1 and Crew 2 with at least 3 agents, required artifacts | M-01 to M-06 |
| Flow handoff, validations, reproducibility, graceful failure | M-07 to M-10 |
| Tech stack and GitHub PRs | M-11 to M-13 |
| Final deliverables | M-14 |

## Corrections to the original Word spec

Changes made while converting; the Word file is unchanged.

1. The Word schema for `sales_predictions` used `store_nbr`, `family`, `predicted_sales`. These are inherited from an earlier dataset proposal and do not exist in M5. The Markdown design uses `store_id` and `item_id` (product-level M5 design, per team instruction). See [database-design.md](database-design.md).
2. The "GitHub" test row of section 13 was partly in Hebrew; it is translated to English above ("a documented PR from each developer, and a README that allows reproduction").
3. Requirement IDs and Mandatory/Optional tags were added; no requirement text was removed.
