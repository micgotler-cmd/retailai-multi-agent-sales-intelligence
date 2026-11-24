# Progress Tracker

Shared development tracker for RetailAI. Requirements: [project-specification.md](project-specification.md). Decisions and open items: [decisions.md](decisions.md). Plan: [implementation-plan.md](implementation-plan.md).

## Project Status

| Field | Value |
|---|---|
| Project name | RetailAI: Multi-Agent Sales Intelligence |
| Current phase | Phase 1 (data foundation) gate passed 2026-11-23. Phase 2 (crews and models): Dev A part (Crew 1, P-04, P-05) complete, Crew 1 gate passed 2026-11-24; Dev B part (P-07 to P-09) not started. Next for Dev A: Flow and Gate 1 (P-10, shared) and the data screens (P-13) |
| Overall status | On track; data pipeline (validation, ETL, cleaning, contract) merged and tested on the real data |
| Last updated | 2026-11-23 |
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
| P-07 | ML | Feature engineering | Dev B | Not Started | | Not Run | Strategy proposed in D-06 |
| P-08 | ML | Model training and evaluation | Dev B | Not Started | | Not Run | Seasonal Naive plus two variants (D-04, D-05) |
| P-09 | Crews | Data Scientist Crew | Dev B | Not Started | | Not Run | M-04 to M-06 |
| P-10 | Flow | CrewAI Flow orchestration | Shared | Not Started | | Not Run | Gates and states in [architecture.md](architecture.md) |
| P-11 | RAG | RAG knowledge base | Shared | Not Started | | Not Run | Optional, deferred (D-14, D-16) |
| P-12 | Agents | Business Recommendation Agent (Agent 7) | Shared | Not Started | | Not Run | Optional, deferred (D-16) |
| P-13 | App | Streamlit dashboard (A: data screens, B: forecasting screens) | Dev A / Dev B | In Progress | `feature/run-reader` | Passed (unit, integration) | D-12 approved 2026-11-24. Dev A plan in 4 steps: (1) read-only run reader `src/repositories/run_artifacts.py`, (2) app shell, run picker and Home, (3) Data Quality, (4) EDA and Business Insights. Step 1 in review: lists runs newest first with status, insights source and LLM usage; loads one run's reports, listing missing and unreadable files instead of failing; refuses run ids that could leave the runs folder; never reads `clean_data.csv` (T-04); strips the fallback marker from `insights.md` |
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
| `feature/run-reader` | `dev` | Read-only run reader for the Streamlit screens (P-13 step 1); D-12 approved | In review | PR into `dev` |

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

## Current Blockers

| Blocker | Affects | Needed from |
|---|---|---|
| Open items (T-05 to T-08, T-10, T-14 to T-21) | Several tasks | Developers, see [decisions.md](decisions.md) |

## Next Actions

1. Michal accepts the Kaggle rules on her own account and downloads the files into `data/raw/` (git-ignored); the files are never shared (T-04 conditions).
2. Milestone PR `dev` into `main` after this gate PR is merged (D-23). Next phase: EDA and insights (P-05) and Crew 1 (P-04) for Dev A; features and baseline on `clean_data.csv` and the contract (P-07, P-08) for Dev B.
3. Done 2026-11-23: spend limit set, local `.env` created, model verified with one approved call (T-01).
4. Run the data steps yourself: `uv run python -m src.data.cleaning` (validation, ETL and cleaning; writes `artifacts/clean/`), then `uv run python -m src.data.contract` (writes `dataset_contract.json` and `contract_check.json`). Single steps: `src.data.validation`, `src.data.etl`, `src.data.inspect_m5`. All outputs are git-ignored; `clean_data.csv` and `long_data.csv` are row-level M5 data and are never committed.
5. Run Crew 1 yourself (calls the OpenAI API; needs a local `.env`; only with the developers' approval): `uv run python -m src.crews.data_analyst_crew`. Outputs and `crew1.log` go to `artifacts/runs/<run_id>/` (git-ignored).
6. Optional milestone PR `dev` into `main` after the Crew 1 gate PR is merged (D-23, "Create a merge commit"). Next for Dev A: the data Streamlit screens (P-13) and, agreed with Dev B, the CrewAI Flow with Gate 1 (P-10).
7. Freeze the workstream interfaces in [agents-and-tasks.md](agents-and-tasks.md) at the end of week 1.

## Decision Log References

| Task | Depends on |
|---|---|
| P-02, P-03 | D-02, D-03, T-02, T-03, T-04, T-13 (Approved) |
| P-04 to P-10 | T-01 (OpenAI), T-11 |
| P-06 | T-12 (Approved) |
| P-07, P-08 | D-04 to D-07, T-09 (Approved), T-16 |
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
