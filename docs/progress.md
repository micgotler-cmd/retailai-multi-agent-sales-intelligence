# Progress Tracker

Shared development tracker for RetailAI. Requirements: [project-specification.md](project-specification.md). Decisions and open items: [decisions.md](decisions.md). Plan: [implementation-plan.md](implementation-plan.md).

## Project Status

| Field | Value |
|---|---|
| Project name | RetailAI: Multi-Agent Sales Intelligence |
| Current phase | Phase 1 (data foundation) gate passed 2026-11-23. Phase 2 (crews and models): Dev A part (Crew 1, P-04, P-05) complete, Crew 1 gate passed 2026-11-24; Dev A data screens (P-13) complete 2026-11-25. Pair-programming switch 2026-11-26: Dev B drives Crew 2 (P-07 to P-09), Dev A reviews |
| Overall status | On track; data pipeline, Crew 1 and the data screens merged and tested; Crew 2 decisions (D-05 to D-07, T-16, T-22, T-23) recorded 2026-11-26, code not started |
| Last updated | 2026-11-26 |
| Next milestone | Week 1 exit: clean data (done) and a working baseline (Dev B, P-07/P-08) ([implementation-plan.md](implementation-plan.md)) |

## Development Progress

Task status: Not Started, In Progress, Blocked, In Review, Completed. Test status: Not Run, Passed, Failed, Not Applicable. Owners show the responsibility role (Dev A, Dev B, Shared) from T-11; A is Lilach, B is Michal ([decisions.md](decisions.md), T-11).

| ID | Component | Task | Owner | Status | Branch / PR | Tests | Notes |
|---|---|---|---|---|---|---|---|
| P-01 | Setup | Repository and environment setup | Shared | Completed | `feature/env-setup`, #5 | Not Applicable | Repo, branches and ruleset done. Python 3.12 environment, `pyproject.toml`, `uv.lock` merged; dependency audit run (D-24). Partner runs `uv sync`; `.env` is created later (needs T-01) |
| P-02 | Data | M5 dataset ingestion | Dev A | Completed | #8, #10 | Passed (unit) | Inspection (`src/data/inspect_m5.py`) and wide-to-long ETL (`src/data/etl.py`) merged. Real data: 38,820 long rows (20 items x 1,941 days) |
| P-03 | Data | Data validation and cleaning | Dev A | Completed | #9, #11 | Passed (unit) | Validation (Agent 1 logic) and cleaning (Agent 2 logic, T-13) merged. Real data: validation pass; 31,278 clean rows, 0 missing prices |
| P-04 | Crews | Data Analyst Crew | Dev A | Completed | #17, #18, #19, #20, `feature/crew1-negative-wording` | Passed (unit, integration, 3 real runs) | M-01 to M-03. Step 1 (settings, logging, LLM factory) #17; step 2 (tools, agents, crew, insights check, per-run caps) #18; step 3 real OpenAI runs (`gpt-4.1-mini`, approved each time). Run 1 2026-11-23 (`20261123-175149-8df956`): completed, 12 calls, 89,793 tokens; template insights (one citation without a number); fixed in #19. Run 2 2026-11-23 (`20261123-182519-44fd68`): completed, 8 calls, 39,918 tokens; template insights (grouped citations not understood, 140 problems); fixed in #20 (grouped citations per clause, no same-unit groups, exact signs, causal claims rejected, 3 attempts with at most 10 problems shown, labeled fallback, attempts and fallback reason logged). Run 3 2026-11-24 (`20261124-164623-7d1d1d`): completed, 10 calls, 44,069 tokens; **Agent 3's own insights saved** on attempt 3 of 3 (attempt 1: 19 problems, same-unit groups; attempt 2: 2 problems, minus signs dropped); all 8 outputs present, no problems. Review of the saved text found one wording issue the check could not see: '-14.7% lower' (a double negative); the check now rejects a negative value followed by 'lower', 'less', 'below' and similar, and the prompt asks for 'a difference of -14.7%' |
| P-05 | Data | EDA and business insights | Dev A | Completed | #16 | Passed (unit) | M-02. `src/data/eda.py` (Agent 3 logic): training period only (T-09); 78 numbered facts in `eda_summary.json`, `eda_report.html` with 8 charts and aggregate tables, template `insights.md` citing fact ids. Normalized per-item metrics; SNAP, event and price findings are associations. The CrewAI agent comes in P-04 |
| P-06 | Data | Dataset Contract | Dev A | Completed | #12 | Passed (unit, e2e) | `src/data/contract.py` writes `dataset_contract.json` (T-12, M-24) and runs the Gate 1 check (9 rules). Real clean data: all rules pass |
| P-07 | ML | Feature engineering | Dev B | Not Started | | Not Run | Strategy approved (D-06, D-07, T-22): lags of 28 days or more, calendar, event and SNAP features known in advance, no price. Rolling-origin dates in [data-and-ml.md](data-and-ml.md) (T-23) |
| P-08 | ML | Model training and evaluation | Dev B | Not Started | | Not Run | Seasonal Naive plus Ridge and Random Forest (D-04, D-05); test and future forecasts, refit policy (T-16, T-22). Two PRs: documentation (`docs/crew2-decisions`), then baseline, MAE and RMSE, `metrics.json` and tests |
| P-09 | Crews | Data Scientist Crew | Dev B | Not Started | | Not Run | M-04 to M-06 |
| P-10 | Flow | CrewAI Flow orchestration | Shared | Not Started | | Not Run | Gates and states in [architecture.md](architecture.md) |
| P-11 | RAG | RAG knowledge base | Shared | Not Started | | Not Run | Optional, deferred (D-14, D-16) |
| P-12 | Agents | Business Recommendation Agent (Agent 7) | Shared | Not Started | | Not Run | Optional, deferred (D-16) |
| P-13 | App | Streamlit dashboard (A: data screens, B: forecasting screens) | Dev A / Dev B | In Progress | #25, #26, #27, #28 | Passed (unit, integration, app smoke) | D-12 approved 2026-11-24. Dev A plan in 4 steps: (1) read-only run reader `src/repositories/run_artifacts.py`, (2) app shell, run picker and Home, (3) Data Quality, (4) EDA and Business Insights. Step 1 merged (#25): lists runs newest first with status, insights source and LLM usage; loads one run's reports, listing missing and unreadable files instead of failing; refuses run ids that could leave the runs folder; never reads `clean_data.csv` (T-04); strips the fallback marker from `insights.md`. Step 2 merged (#26): `app/streamlit_app.py` with navigation (Overview, Data) and a sidebar run picker (default: newest completed run; the choice is kept across pages); Home shows the pipeline, the data scope, the selected run's status, insights source, fallback reason, problems, LLM calls and tokens, and the 8 Crew 1 files; Data Quality, EDA and Insights are placeholders until steps 3 and 4; `.streamlit/config.toml` turns usage statistics off and serves on localhost only; 15 `AppTest` smoke tests. Step 3 merged (#27): Data Quality page with four sections from the run's reports: validation (11 checks with status, blocking flag and message), cleaning (rows in and out, the three T-13 actions with counts, first sale and rows dropped per product), fields and missing values from the contract (type, allowed values or range, missing-value rule, assumptions, limitations), and Gate 1 (the 9 contract rules); missing or broken files give a message and the other sections still show; no data rows; checked on the real run 3. Step 4 merged (#28, completes the Dev A screens): EDA page embeds `eda_report.html` (generated by Python, no scripts; a report with scripts, event handlers or embedded frames is not embedded, only offered as a download) with a download button; Business Insights page shows `insights.md` as plain Markdown (no raw HTML) under a clear label (written by the agent, with the accepted attempt, or template fallback with the reason; older runs labeled from `crew1_report.json`), six charts drawn from the `eda_summary.json` tables (category, demand group, weekday, month, SNAP vs other days, event types vs no event; association, not causal), a table view under each chart, and the list of all facts cited as [Fnn]; chart colors validated for color-vision deficiency in light and dark mode. Remaining for P-13: Dev B's Forecast and Model Evaluation pages, shared Run History |
| P-14 | Storage | Supabase integration | Shared | Not Started | | Not Run | Optional, deferred (D-15); LocalRepository comes first (D-08) |
| P-15 | Testing | Unit and integration testing | Shared | In Progress | #8 to #12 | Passed | 136 unit tests for the data layer on synthetic data; integration tests come with the crews and the Flow. [testing-strategy.md](testing-strategy.md) |
| P-16 | Testing | End-to-end validation | Shared | In Progress | #13, `feature/phase-gate-crew1` | Passed | `tests/e2e/test_data_pipeline.py`: validation, ETL, cleaning and contract through the CLIs on synthetic data (also reproducibility and graceful failure on corrupt input) and on the real data when `data/raw/` exists. `tests/e2e/test_crew1.py` (Crew 1 gate): the full crew through its runner with a scripted fake LLM (no API call): all 8 outputs, quality and contract checks pass, the crew's `clean_data.csv` is byte-identical to the pipeline's, no data row appears in any LLM prompt; synthetic and real data. Extended at each phase gate; the full run with both crews and the Flow comes later |
| P-17 | Delivery | Final presentation and demo | Shared | Not Started | | Not Applicable | 10-12 slides and a demo of at most 5 minutes (M-14) |

## Branches and Pull Requests

| Branch | Base | Purpose | Status | PR |
|---|---|---|---|---|
| `main` | n/a | Production, default branch (D-23) | Protected by ruleset (PR required) | #1, #4 merged from `dev` |
| `dev` | `main` | Integration branch (D-23) | Protected by ruleset (PR required) | #2 merged from `main` |
| `docs/add-simple-plan` | `dev` | Simple-language plan overview (`project-plan-simple.html`) | Merged | #3 |
| `feature/env-setup` | `dev` | Python 3.12 environment with uv (D-13) | Merged | #5 |
| `docs/finalize-decisions` | `dev` | Record T-01, T-02, T-03, T-04, T-11, T-12 | Merged | #6 |
| `docs/t04-kaggle-terms` | `dev` | Record the Kaggle M5 terms check (T-04) | Merged | #7 |
| `feature/data-inspection` | `dev` | Read-only M5 inspection; T-09 split and T-03 items (P-02) | Merged | #8 |
| `feature/data-validation` | `dev` | Data Validator logic and `quality_report.json` (P-03) | Merged | #9 |
| `feature/etl-long` | `dev` | Wide-to-long ETL for the approved items (P-02) | Merged | #10 |
| `feature/data-cleaning` | `dev` | Cleaning rules (T-13) and `clean_data.csv` (P-03) | Merged | #11 |
| `feature/dataset-contract` | `dev` | Dataset contract and Gate 1 check (P-06) | Merged | #12 |
| `feature/phase-gate-data` | `dev` | End-to-end data pipeline test and phase gate record | Merged | #13 |
| `dev` (release) | `main` | Data foundation release | Merged | #14 |
| `main` (sync) | `dev` | Align history after the squash-merged release | Merged | #15 |
| `feature/eda-insights` | `dev` | EDA and insights, Agent 3 logic (P-05) | Merged | #16 |
| `feature/config-logging` | `dev` | Settings, redacting logging, LLM factory (P-04 step 1) | Merged | #17 |
| `feature/analyst-crew` | `dev` | Crew 1 tools, agents, crew and runner (P-04 step 2) | Merged | #18 |
| `feature/crew1-run-fixes` | `dev` | Fixes from the first real Crew 1 run; T-01 recorded | Merged | #19 |
| `feature/insights-check-v2` | `dev` | Insights check: grouped citations, no swaps, causal claims, retry limit, labeled fallback | Merged | #20 |
| `feature/crew1-negative-wording` | `dev` | Third real run recorded; double-negative check; P-04 completed | Merged | #21 |
| `feature/phase-gate-crew1` | `dev` | Crew 1 phase gate: security review, e2e test, pip-audit; report redaction fix | Merged | #22 |
| `feature/run-reader` | `dev` | Read-only run reader for the Streamlit screens (P-13 step 1); D-12 approved | Merged | #25 |
| `feature/app-shell-home` | `dev` | Streamlit app shell, run picker and Home page (P-13 step 2) | Merged | #26 |
| `feature/data-quality-page` | `dev` | Data Quality page (P-13 step 3) | Merged | #27 |
| `feature/eda-insights-pages` | `dev` | EDA and Business Insights pages (P-13 step 4) | Merged | #28 |
| `docs/handover-crew2` | `dev` | Handover note for Dev B (Crew 2); pair-programming switch | Merged | #29 |
| `docs/crew2-decisions` | `dev` | Record D-05 to D-07, T-16, T-22, T-23 for Crew 2 (documentation only) | In review (Dev A reviews) | PR into `dev` |

Add one row per feature branch and its PR (target `dev`) as work starts.

## Completed Work

| Date | Milestone | PR |
|---|---|---|
| 2026-11-17 | Documentation set created (README, CLAUDE.md, 10 documents under `docs/`) and internal links checked | Initial commit `82aeec9` on `main` (no PR) |
| 2026-11-17 | Public GitHub repository created and `main` pushed | n/a |
| 2026-11-17 | `dev` branch created, ruleset for `main` and `dev` enabled, branching strategy documented (D-23) | #1, #2 |
| 2026-11-18 | Second developer is a collaborator and has cloned the repository | n/a |
| 2026-11-18 | Simple-language plan overview added to `dev` and `main` | #3, #4 |
| 2026-11-18 | Planning decisions recorded: T-11 (responsibilities), T-01 (OpenAI provider), T-02 (`CA_1`), T-03 (approach), T-12 (JSON contract); T-04 pending. Documentation only; no development task is complete | #6 |
| 2026-11-18 | Python 3.12 environment merged (P-01) | #5 |
| 2026-11-18 | Kaggle M5 terms checked and recorded (T-04): allowed for education, with conditions | #7 |
| 2026-11-18 | Roles confirmed: Lilach is Developer A, Michal is Developer B (T-11). M5 data downloaded by Lilach | n/a |
| 2026-11-23 | Split (T-09) and product selection (T-03) approved; 20 `CA_1` items selected by deterministic stratified spread | #8 |
| 2026-11-23 | Data Validator logic and `quality_report.json` (P-03) | #9 |
| 2026-11-23 | Wide-to-long ETL for the 20 items; P-02 completed | #10 |
| 2026-11-23 | Cleaning rules (T-13) and `clean_data.csv`; P-03 completed | #11 |
| 2026-11-23 | Dataset contract and Gate 1 check; P-06 completed | #12 |
| 2026-11-23 | **Phase gate passed (data foundation):** e2e test 5/5 including the real data; security review with no findings; `pip-audit` shows only the 5 known `chromadb` advisories (D-24), no new ones | #13 |
| 2026-11-23 | Data foundation released to `main`; histories aligned (use merge commits for releases) | #14, #15 |
| 2026-11-23 | EDA facts, report and insights (Agent 3 logic); P-05 completed | #16 |
| 2026-11-23 | Crew 1 settings, logging, tools, agents, crew and LLM budget (P-04 steps 1 and 2) | #17, #18 |
| 2026-11-24 | Three real Crew 1 runs; insights check improved; Agent 3's own insights pass; P-04 completed | #19, #20, #21 |
| 2026-11-24 | **Phase gate passed (Crew 1):** e2e 7/7 including the real data (data pipeline 5, Crew 1 2); full suite 299 passed; security review of the code since the last gate (`06fcf91`): key held in `Secret` and revealed only to the LLM client, all log lines redacted, CrewAI telemetry and tracing off (the three real runs contacted only `api.openai.com`), no key-like strings in any run folder, HTML report escaped, tools bound to the run folder with no path input, no data rows to the LLM, no eval/exec/pickle/subprocess; one low-severity finding fixed: `crew1_report.json` stored error messages and agent answers unredacted, now redacted like the logs (regression test added); `pip-audit`: only the 5 known `chromadb` advisories (D-24), no dependency changes since the last gate | `feature/phase-gate-crew1` |
| 2026-11-24 | EDA and Crew 1 released to `main`; histories aligned | #23, #24 |
| 2026-11-25 | Dev A's data screens (P-13 steps 1 to 4) | #25 to #28 |
| 2026-11-26 | Handover to Dev B for Crew 2; pair programming | #29 |
| 2026-11-26 | Crew 2 decisions drafted for review: D-05, D-06, D-07, T-16 (refit policy), T-22 (test and future forecasts), T-23 (Seasonal Naive definition, three rolling-origin windows). Documentation only; no code | PR pending |

## Handover to Dev B: Crew 2 (2026-11-26)

We work in pair programming, one task at a time: one developer drives (with their own Claude Code session) and the other watches and reviews. Dev A (Lilach) drove the data foundation, Crew 1 and the data screens (PRs #7 to #28). **Dev B (Michal) now drives Crew 2 (P-07 to P-09); Dev A watches and approves Dev B's PRs.** This section is the starting point for Dev B's Claude session.

**State on `dev` (6d8fa90):** data pipeline, Crew 1 and the four data screens are complete and tested (361 tests); phase gates passed for the data foundation and Crew 1; released to `main` up to the Crew 1 gate (#23). Nothing exists yet in `src/ml/`, `src/flows/` or for Crew 2.

**First steps for Dev B:**
1. Accept the Kaggle rules with your own account and download the M5 files into `data/raw/` (T-04: each developer uses their own copy; never shared or committed).
2. Build the clean data locally: `uv run python -m src.data.cleaning`, then `uv run python -m src.data.contract` (outputs in `artifacts/clean/`, git-ignored). Expected: 31,278 rows, contract check `pass`. Or use the outputs of a Crew 1 run in `artifacts/runs/<run_id>/`.
3. (Drafted 2026-11-26 in `docs/crew2-decisions`, pending Dev A's review.) Confirm the open model decisions with Dev A and record them in [decisions.md](decisions.md) before training: **D-05** (Ridge and Random Forest), **D-06** (direct forecast with lags of 28 days or more, plus known calendar and SNAP features), **D-07** (`sell_price` not a model feature), **T-16** (refit on train plus validation before the test forecast, or not; document either way). **D-04** (Seasonal Naive baseline plus two variations, MAE and RMSE) is approved.

**Inputs (from Crew 1):** `clean_data.csv` and `dataset_contract.json` ([agents-and-tasks.md](agents-and-tasks.md) interfaces; field list in [data-and-ml.md](data-and-ml.md)). Gate 1 is `contract_check.json` with status `pass` (`src/data/contract.py`, `check_against_contract`). The approved split is in `config/data_scope.json`: train d_1 to d_1885, validation d_1886 to d_1913, test d_1914 to d_1941 (T-09); the test period is never used for training or tuning. The 28-day horizon is `horizon_days`.

**Outputs required (M-04 to M-06):** `features.csv`, `model.joblib` (or `.pkl`), `evaluation_report.md`, `model_card.md` (purpose, training data, metrics, limitations, ethics), plus `forecast.csv` and `metrics.json` as in the interfaces table. Gate 2 ([architecture.md](architecture.md)): required features exist, model and forecast files exist, the forecast covers 28 days for every selected item, metrics come from the chronological holdout.

**Patterns to reuse from Crew 1:**
- Logic in `src/ml/` as plain, tested Python; agents never compute metrics (CLAUDE.md).
- Thin tools bound to one run folder, returning short JSON summaries and no data rows to the LLM: `src/tools/data_tools.py` (`RunPaths`, `ToolRefused` for missing prerequisites).
- Agents (definitions only, no delegation, capped `max_iter`): `src/agents/data_analyst_agents.py`. Crew and runner (run folder, output checks, `crew1_report.json`, fallback rules): `src/crews/data_analyst_crew.py`.
- LLM settings and cost caps: `src/utils/config.py`, `src/utils/llm.py` (telemetry off), `src/utils/llm_budget.py` (per-run call and token caps); redacting logs in `src/utils/logging_setup.py`.
- Tests: scripted fake LLM `tests/fake_llm.py` (no network, no cost), network guard in `tests/integration/test_data_analyst_crew.py`, synthetic M5 fixture in `tests/conftest.py`, end-to-end tests in `tests/e2e/`.
- Screens: Dev B's Forecast and Model Evaluation pages plug into `app/streamlit_app.py` as described in the Streamlit app row of the interfaces table; Crew 2 file names are added to `src/repositories/run_artifacts.py`.

**Rules that stay in force:** small PRs into `dev` with tests (including a failure case) and `progress.md` updated; Dev A approves; no OpenAI call without both developers' approval (each real run is approved separately; tests mock the LLM); never commit `.env`, data, models or artifacts; phase gate (security review and end-to-end test) before the next phase.

**Shared work after Crew 2:** the CrewAI Flow with Gate 1 and Gate 2 (P-10) and the Run History screen; then the MVP gate before any optional work (Agent 7, RAG, Supabase).

## Current Blockers

| Blocker | Affects | Needed from |
|---|---|---|
| Open items (T-05 to T-08, T-10, T-14 to T-21) | Several tasks | Developers, see [decisions.md](decisions.md) |

## Next Actions

1. Dev B drives Crew 2 (P-07 to P-09): see [Handover to Dev B](#handover-to-dev-b-crew-2-2026-11-26) above; the data download and clean data are done on Dev B's machine; the model decisions are drafted in the documentation PR `docs/crew2-decisions`. After Dev A's review, next is the baseline PR (Seasonal Naive, MAE and RMSE, `metrics.json`, unit tests).
2. Done 2026-11-24: data foundation and Crew 1 released to `main` (#14, #23); histories aligned (#15, #24).
3. Done 2026-11-23: spend limit set, local `.env` created, model verified with one approved call (T-01).
4. Run the data steps yourself: `uv run python -m src.data.cleaning` (validation, ETL and cleaning; writes `artifacts/clean/`), then `uv run python -m src.data.contract` (writes `dataset_contract.json` and `contract_check.json`). Single steps: `src.data.validation`, `src.data.etl`, `src.data.inspect_m5`. All outputs are git-ignored; `clean_data.csv` and `long_data.csv` are row-level M5 data and are never committed.
5. Run Crew 1 yourself (calls the OpenAI API; needs a local `.env`; only with the developers' approval): `uv run python -m src.crews.data_analyst_crew`. Outputs and `crew1.log` go to `artifacts/runs/<run_id>/` (git-ignored).
6. Done 2026-11-25: Dev A's data screens (P-13 steps 1 to 4, #25 to #28). Next shared work after Crew 2: the Flow with Gate 1 and Gate 2 (P-10) and Run History; release the screens to `main` at the next phase gate.
7. Freeze the workstream interfaces in [agents-and-tasks.md](agents-and-tasks.md) at the end of week 1.

## Decision Log References

| Task | Depends on |
|---|---|
| P-02, P-03 | D-02, D-03, T-02, T-03, T-04, T-13 (Approved) |
| P-04 to P-10 | T-01 (OpenAI), T-11 |
| P-06 | T-12 (Approved) |
| P-07, P-08 | D-04 to D-07, T-09, T-16, T-22, T-23 (all Approved; recorded 2026-11-26) |
| P-11, P-12 | D-14, D-16, T-14 |
| P-13 | D-12 |
| P-14 | D-08 to D-11, D-15 |

Full list: [decisions.md](decisions.md).

## Update Rules

Update this file in the same PR whenever:

- a task begins,
- a task is completed,
- a PR is merged,
- a blocker is found or resolved,
- a milestone is reached.

Also refresh [project-plan-simple.html](project-plan-simple.html) (the plain-language overview, section "Where we are now") whenever the status changes.

Mark a task Completed only after the work has been done and validated, with its tests Passed. Generating files does not count as completion.
