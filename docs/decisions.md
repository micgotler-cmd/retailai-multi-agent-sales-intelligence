# Decisions and Open Items

Single place for architectural decisions and every `TBD`. Requirements are in [project-specification.md](project-specification.md); this file records choices and what is still open.

**Status values:** **Approved** (stated in the spec, the brief, or by the team) | **Proposed** (recommended, awaiting team confirmation) | **Deferred** (intentionally postponed, with a trigger).

## Decision log

| ID | Decision | Status | Rationale / source | Details |
|---|---|---|---|---|
| D-01 | Exactly two CrewAI crews with 3 agents each, plus an independent Agent 7 that runs once after the Forecast Validation Gate | Approved | Spec s1, s6, s7; brief M-01 | [architecture.md](architecture.md), [agents-and-tasks.md](agents-and-tasks.md) |
| D-02 | M5 Forecasting - Accuracy (Walmart) is the planning dataset | Approved | Spec s5; the brief allows any dataset. Terms checked 2026-11-18: allowed for education, with conditions (T-04) | [data-and-ml.md](data-and-ml.md) |
| D-03 | Forecast target: daily units, 28-day horizon, per `item_id` x `store_id` | Approved | Spec s8 | [data-and-ml.md](data-and-ml.md) |
| D-04 | Compare a Seasonal Naive baseline with two Scikit-Learn model variations on MAE and RMSE, chronological split | Approved | Spec s8 (brief minimum is 2 variations) | [data-and-ml.md](data-and-ml.md) |
| D-05 | The two variations are Ridge Regression and Random Forest Regressor | Proposed | Spec says "such as"; cheap and explainable | [data-and-ml.md](data-and-ml.md) |
| D-06 | Multi-step strategy: direct forecast using only lags and rolling windows available at forecast time (lags of 28 days or more), plus known calendar/SNAP features; recursive lags 7/14 as a stretch variant | Proposed | Spec allows "recursive ... or another leakage-safe strategy" | [data-and-ml.md](data-and-ml.md) |
| D-07 | `sell_price` is excluded from the MVP model features (future prices unknown); used in EDA only | Proposed | Spec: "prices only when available at prediction time" | [data-and-ml.md](data-and-ml.md) |
| D-08 | Repository abstraction with `LocalRepository` first; the pipeline must run fully without Supabase | Approved | Spec s10A | [database-design.md](database-design.md) |
| D-09 | Database tables use `store_id` and `item_id` (not `store_nbr`/`family`) | Approved | Team instruction; product-level M5 design | [database-design.md](database-design.md) |
| D-10 | Store recommendations in a separate `recommendations` table rather than in `business_insights` | Proposed | Stricter schema (status, evidence array); fallback is `business_insights` with a type value | [database-design.md](database-design.md) |
| D-11 | `LocalRepository` is backed by SQLite (one file per run folder or one project DB) | Proposed | Same queries as Supabase; no extra service. Alternative: JSON files | [database-design.md](database-design.md) |
| D-12 | UI framework is Streamlit | Proposed | Spec describes Streamlit; brief allows Streamlit or Flask | [architecture.md](architecture.md) |
| D-13 | Python 3.12 environment managed with `uv` (`pyproject.toml`, `uv.lock`) | Approved | System Python is 3.14, outside CrewAI's supported range; set up in the env-setup PR | [implementation-plan.md](implementation-plan.md) |
| D-14 | RAG backend: CrewAI Knowledge or a local Chroma store | Deferred | Decide after a compatibility check with the pinned CrewAI version (during the RAG timebox) | [rag-and-recommendations.md](rag-and-recommendations.md) |
| D-15 | Connect Supabase (migrations, `SupabaseRepository`, Streamlit history) | Deferred | Spec: week 3 or later, after the local MVP works | [database-design.md](database-design.md) |
| D-16 | Build Agent 7 and RAG | Deferred | Start after the MVP gate (end of week 3, end-to-end local run); 4-6 h timebox | [rag-and-recommendations.md](rag-and-recommendations.md) |
| D-17 | Cloud deployment (Streamlit Cloud / Railway) | Deferred | Optional in the brief and spec | [implementation-plan.md](implementation-plan.md) |
| D-18 | Git workflow: one PR per task, reviewed by the other developer (branch model is defined in D-23) | Proposed | Brief requires PRs; spec s13 requires a documented PR from each developer | [implementation-plan.md](implementation-plan.md) |
| D-19 | GitHub repo `retailai-multi-agent-sales-intelligence`, private initially, default branch `main` | Approved | Team instruction. Creation still needs explicit go-ahead | [implementation-plan.md](implementation-plan.md) |
| D-21 | Repository layout: `src/{agents,crews,flows,data,ml,rag,repositories,utils}`, `app/`, `tests/{unit,integration,e2e}`, `knowledge/`, `artifacts/`, `config/` | Approved | Team instruction; supersedes the earlier proposed layout in the first docs draft | [architecture.md](architecture.md) |
| D-22 | Progress is tracked in `docs/progress.md`, updated in the relevant PR | Approved | Team instruction | [progress.md](progress.md) |
| D-23 | Two permanent branches: `main` (production, default branch) and `dev` (integration). Feature branches start from `dev` and merge into `dev` by PR; `dev` merges into `main` by PR at stable milestones; no direct commits to `main` after the initial setup. No automatic deployments and no separate Supabase environments yet | Approved | Team instruction; remote branch protection pending approval | [implementation-plan.md](implementation-plan.md) |
| D-24 | Accepted risk: `chromadb` (pulled in by `crewai`) has 5 advisories with no fixed version (server code injection with `trust_remote_code`, authorization flaws in Chroma server mode). Mitigation: never run a Chroma server, never enable `trust_remote_code`, use local embedded mode only; re-audit with `pip-audit` at every phase gate | Approved | Dependency audit during env setup | [progress.md](progress.md) |
| D-20 | Documentation layout: requirements only in `project-specification.md`, decisions only here, other docs cross-reference | Approved | Team instruction | [../README.md](../README.md) |

## Finalized items (formerly open, decided 2026-11-18)

Status values as above, plus **Pending** for the part of a decision that still needs verification or input. Details live in the linked documents.

| ID | Decision | Status | Still pending | Details |
|---|---|---|---|---|
| T-11 | Developer responsibilities. **A:** M5 ingestion and preprocessing, validation and cleaning, EDA, dataset contract, Data Analyst Crew, data Streamlit screens. **B:** feature engineering, model training and evaluation, 28-day product-level forecasting, Data Scientist Crew, forecasting Streamlit screens. **Shared:** CrewAI Flow orchestration and integration, Agent 7, RAG, Supabase, end-to-end testing, final presentation and demo. Interfaces between workstreams are defined so A and B can work in parallel. Developer A is Lilach, Developer B is Michal (T-11, confirmed 2026-11-18) | Approved | | [agents-and-tasks.md](agents-and-tasks.md) |
| T-01 | OpenAI API is the LLM provider for all seven agents at runtime; Claude Code stays the development tool. Provider and model come from environment variables (`OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_FALLBACK_MODEL`); nothing is hard-coded. Proposed default `gpt-4.1-mini`, fallback `gpt-4o-mini`. Cost controls: temperature 0, limited retries, per-run call and token caps, spend limit in the OpenAI dashboard. Deterministic Python does all numeric work | Approved (provider); model and budget Pending | Live availability check of the model (one approved API call), CrewAI-compatible structured output check, monthly budget amount, per-run caps tuned after the first real run | [architecture.md](architecture.md) |
| T-02 | MVP store is `CA_1`. The store is a configuration value so another store can be chosen later; the MVP implements one store only | Approved | | [data-and-ml.md](data-and-ml.md) |
| T-03 | Product selection, approved 2026-11-23. Store `CA_1`, 20 products (expandable to 50 with the same method). Eligibility on the training period only (d_1 to d_1885): at least 365 days of history, at most 80% zero-sales days, at least 95% price coverage (history and coverage are measured from the first observed sale, see data-and-ml.md). Demand groups: 7 high, 7 medium, 6 low by mean daily units. Within each group, deterministic stratified spread over the demand range (no random seed). Result: 2,528 of 3,049 items eligible, 842-843 per group. Selected: high: `FOODS_3_234`, `FOODS_1_162`, `HOUSEHOLD_1_494`, `FOODS_3_208`, `HOUSEHOLD_1_180`, `FOODS_3_190`, `FOODS_3_433`; medium: `FOODS_2_189`, `FOODS_3_060`, `FOODS_2_107`, `HOUSEHOLD_1_299`, `FOODS_3_488`, `HOUSEHOLD_1_091`, `FOODS_1_015`; low: `HOUSEHOLD_2_219`, `FOODS_3_427`, `FOODS_2_007`, `FOODS_2_179`, `HOUSEHOLD_2_003`, `HOBBIES_1_002` | Approved | | [data-and-ml.md](data-and-ml.md) |
| T-04 | Kaggle M5 Forecasting - Accuracy terms checked on 2026-11-18 by Lilach Afik (<https://www.kaggle.com/competitions/m5-forecasting-accuracy/rules>, section 7 "Competition Data"; the Data tab license is "Subject to Competition Rules"). Rule 7A allows non-commercial use, "including ... for academic research and education", so coursework use is allowed. Rule 7B forbids transmitting, duplicating, publishing or redistributing the data to anyone who has not agreed to the rules. Rule 7C (external data) applies only to competition entries and does not affect us. Conditions: (1) each developer accepts the rules on their own Kaggle account and downloads their own copy; (2) no M5 data in the public repository: no raw files and no row-level copies such as `clean_data.csv`; (3) anyone else who runs the project (for example graders) downloads the data from Kaggle themselves; (4) slides, demo and dashboard show aggregates, charts, metrics and forecasts only, with no raw data tables or data downloads; a public deployment (D-17) needs a fresh check; (5) if Supabase ever holds M5-derived rows, the project stays private to the two developers; (6) LLM agents receive summaries, statistics and metrics, not bulk raw rows | Approved (with conditions) | | [data-and-ml.md](data-and-ml.md) |
| T-12 | Versioned JSON dataset contract, `dataset_contract.json`, with deterministic hand-written Python validation (no schema-management framework) | Approved | Exact field list is finalized when the first clean data exists | [data-and-ml.md](data-and-ml.md) |
| T-09 | Train/validation/test split, approved 2026-11-23, chronological only. Train d_1 to d_1885 (2011-01-29 to 2016-03-27); validation d_1886 to d_1913 (2016-03-28 to 2016-04-24); test d_1914 to d_1941 (2016-04-25 to 2016-05-22), from `sales_train_evaluation.csv`. The test period is excluded from model selection, hyperparameter tuning, product selection and feature engineering decisions. After model selection on validation, retraining on train plus validation is permitted before the final test evaluation (T-16). Lags, rolling statistics and covariates must use only information available at the forecast origin over the full 28-day horizon | Approved | | [data-and-ml.md](data-and-ml.md) |

## Open items (TBD)

| ID | Open item | Needed by | Notes |
|---|---|---|---|
| T-05 | Supabase project (exists? who owns it?) and how each developer holds keys | Week 3 | Only if D-15 goes ahead |
| T-06 | Second developer's GitHub username | Before repo setup | For collaborator invite |
| T-07 | Commit the eight final artifacts to Git at submission, or keep them local | Week 4 | Datasets and `.env` are never committed; row-level M5 data is excluded (T-04) |
| T-08 | Instructor confirmation that extensions (Agent 7, RAG, Supabase) are acceptable | Before week 3 | Spec s17 |
| T-10 | Review of the supplementary PDF named in spec s19 | Week 1 | Not available in this repository |
| T-13 | Missing-price null policy | Week 1 | Examine, do not silently impute (spec s5) |
| T-14 | How Agent 7 picks the item(s) for its single recommendation | Before D-16 | Spec: "one qualified recommendation" |
| T-15 | Deployment target, if any | Week 4 | Linked to D-17 |
| T-16 | Whether to refit the final model on train plus validation before the test forecast | Week 2 | Permitted by T-09; whether we do it must be documented either way |
| T-17 | Supabase failure fallback policy (queue unsent records for retry or not) | Week 3 | Only if D-15 goes ahead |
| T-18 | Exact UNIQUE key for `business_insights` (insight granularity) | Week 3 | Needed for idempotent retries |
| T-21 | Embedding model for RAG (OpenAI embeddings suggested, name to verify with the pinned CrewAI version); only needed if Agent 7 goes ahead | Before D-16 | Split out of T-01 |
| T-20 | Location of CrewAI tool wrappers and Supabase SQL migrations (not in the approved layout) | Week 1 / Week 3 | |
| T-19 | Project start date (the plan chart uses placeholder dates) | Week 1 | |
