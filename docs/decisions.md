# Decisions and Open Items

Single place for architectural decisions and every `TBD`. Requirements are in [project-specification.md](project-specification.md); this file records choices and what is still open.

**Status values:** **Approved** (stated in the spec, the brief, or by the team) | **Proposed** (recommended, awaiting team confirmation) | **Deferred** (intentionally postponed, with a trigger).

## Decision log

| ID | Decision | Status | Rationale / source | Details |
|---|---|---|---|---|
| D-01 | Exactly two CrewAI crews with 3 agents each, plus an independent Agent 7 that runs once after the Forecast Validation Gate | Approved | Spec s1, s6, s7; brief M-01 | [architecture.md](architecture.md), [agents-and-tasks.md](agents-and-tasks.md) |
| D-02 | M5 Forecasting - Accuracy (Walmart) is the planning dataset | Approved | Spec s5; the brief allows any dataset. Rights check open (T-04) | [data-and-ml.md](data-and-ml.md) |
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
| D-13 | Python 3.12 environment managed with `uv` | Proposed | System Python is 3.14, outside CrewAI's supported range | [implementation-plan.md](implementation-plan.md) |
| D-14 | RAG backend: CrewAI Knowledge or a local Chroma store | Deferred | Decide after a compatibility check with the pinned CrewAI version (during the RAG timebox) | [rag-and-recommendations.md](rag-and-recommendations.md) |
| D-15 | Connect Supabase (migrations, `SupabaseRepository`, Streamlit history) | Deferred | Spec: week 3 or later, after the local MVP works | [database-design.md](database-design.md) |
| D-16 | Build Agent 7 and RAG | Deferred | Start after the MVP gate (end of week 3, end-to-end local run); 4-6 h timebox | [rag-and-recommendations.md](rag-and-recommendations.md) |
| D-17 | Cloud deployment (Streamlit Cloud / Railway) | Deferred | Optional in the brief and spec | [implementation-plan.md](implementation-plan.md) |
| D-18 | Git workflow: one PR per task, reviewed by the other developer (branch model is defined in D-23) | Proposed | Brief requires PRs; spec s13 requires a documented PR from each developer | [implementation-plan.md](implementation-plan.md) |
| D-19 | GitHub repo `retailai-multi-agent-sales-intelligence`, private initially, default branch `main` | Approved | Team instruction. Creation still needs explicit go-ahead | [implementation-plan.md](implementation-plan.md) |
| D-21 | Repository layout: `src/{agents,crews,flows,data,ml,rag,repositories,utils}`, `app/`, `tests/{unit,integration,e2e}`, `knowledge/`, `artifacts/`, `config/` | Approved | Team instruction; supersedes the earlier proposed layout in the first docs draft | [architecture.md](architecture.md) |
| D-22 | Progress is tracked in `docs/progress.md`, updated in the relevant PR | Approved | Team instruction | [progress.md](progress.md) |
| D-23 | Two permanent branches: `main` (production, default branch) and `dev` (integration). Feature branches start from `dev` and merge into `dev` by PR; `dev` merges into `main` by PR at stable milestones; no direct commits to `main` after the initial setup. No automatic deployments and no separate Supabase environments yet | Approved | Team instruction; remote branch protection pending approval | [implementation-plan.md](implementation-plan.md) |
| D-20 | Documentation layout: requirements only in `project-specification.md`, decisions only here, other docs cross-reference | Approved | Team instruction | [../README.md](../README.md) |

## Open items (TBD)

| ID | Open item | Needed by | Notes |
|---|---|---|---|
| T-01 | LLM provider/model and embedding model, API budget | Week 1 (crews), Agent 7 | Keys only in `.env` (M-21) |
| T-02 | MVP store | Week 1 | `CA_1` suggested, not confirmed |
| T-03 | Number of items (20-50) and selection rule (history coverage, zero rate, department mix) | Week 1 | After data inspection |
| T-04 | M5 usage rights / Kaggle terms for coursework | Week 1 | Download needs a Kaggle login (manual) |
| T-05 | Supabase project (exists? who owns it?) and how each developer holds keys | Week 3 | Only if D-15 goes ahead |
| T-06 | Second developer's GitHub username | Before repo setup | For collaborator invite |
| T-07 | Commit the eight final artifacts to Git at submission, or keep them local | Week 4 | Datasets and `.env` are never committed |
| T-08 | Instructor confirmation that extensions (Agent 7, RAG, Supabase) are acceptable | Before week 3 | Spec s17 |
| T-09 | Exact train/validation/test boundaries | After data inspection | Provisional: test = the last 28 days of history |
| T-10 | Review of the supplementary PDF named in spec s19 | Week 1 | Not available in this repository |
| T-11 | Which developer is A and which is B | Week 1 | Roles in spec s15 |
| T-12 | Dataset contract format (JSON Schema vs custom JSON) | Week 1 | Must hold schema, allowed values, assumptions, constraints |
| T-13 | Missing-price null policy | Week 1 | Examine, do not silently impute (spec s5) |
| T-14 | How Agent 7 picks the item(s) for its single recommendation | Before D-16 | Spec: "one qualified recommendation" |
| T-15 | Deployment target, if any | Week 4 | Linked to D-17 |
| T-16 | Refit the final model on train plus validation before the test forecast | Week 2 | Must be documented either way |
| T-17 | Supabase failure fallback policy (queue unsent records for retry or not) | Week 3 | Only if D-15 goes ahead |
| T-18 | Exact UNIQUE key for `business_insights` (insight granularity) | Week 3 | Needed for idempotent retries |
| T-20 | Location of CrewAI tool wrappers and Supabase SQL migrations (not in the approved layout) | Week 1 / Week 3 | |
| T-19 | Project start date (the plan chart uses placeholder dates) | Week 1 | |
