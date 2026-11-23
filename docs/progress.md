# Progress Tracker

Shared development tracker for RetailAI. Requirements: [project-specification.md](project-specification.md). Decisions and open items: [decisions.md](decisions.md). Plan: [implementation-plan.md](implementation-plan.md).

## Project Status

| Field | Value |
|---|---|
| Project name | RetailAI: Multi-Agent Sales Intelligence |
| Current phase | Phase 0: repository and documentation setup (no application code yet) |
| Overall status | On track; documentation, repository and environment done; data terms checked (T-04) |
| Last updated | 2026-11-18 |
| Next milestone | Week 1 exit: clean data and a working baseline ([implementation-plan.md](implementation-plan.md)) |

## Development Progress

Task status: Not Started, In Progress, Blocked, In Review, Completed. Test status: Not Run, Passed, Failed, Not Applicable. Owners show the responsibility role (Dev A, Dev B, Shared) from T-11; A is Lilach, B is Michal ([decisions.md](decisions.md), T-11).

| ID | Component | Task | Owner | Status | Branch / PR | Tests | Notes |
|---|---|---|---|---|---|---|---|
| P-01 | Setup | Repository and environment setup | Shared | Completed | `feature/env-setup`, #5 | Not Applicable | Repo, branches and ruleset done. Python 3.12 environment, `pyproject.toml`, `uv.lock` merged; dependency audit run (D-24). Partner runs `uv sync`; `.env` is created later (needs T-01) |
| P-02 | Data | M5 dataset ingestion | Dev A | In Progress | `feature/data-inspection` | Passed (unit) | Step 1, read-only inspection (`src/data/inspect_m5.py`) done: files and columns verified, calendar has no gaps, `sales_train_validation` is an exact prefix of `sales_train_evaluation`. Split (T-09) and 20 items (T-03) approved and recorded 2026-11-23. Next: ETL wide-to-long |
| P-03 | Data | Data validation and cleaning | Dev A | Not Started | | Not Run | Null-price policy TBD (T-13) |
| P-04 | Crews | Data Analyst Crew | Dev A | Not Started | | Not Run | M-01 to M-03. Plan: move the reusable checks from `src/data/inspect_m5.py` (files, columns, calendar gaps, duplicates, negative values) into `src/data/validation.py` as the Data Validator tools, so the logic exists once; put the 20 approved item IDs and the T-09 split days in a config file under `config/` for the Data Cleaner and the contract; keep `inspect_m5` as a dev script (rerun to expand to 50 items) that imports the shared checks. The crew never re-selects items at runtime |
| P-05 | Data | EDA and business insights | Dev A | Not Started | | Not Run | M-02 |
| P-06 | Data | Dataset Contract | Dev A | Not Started | | Not Run | Versioned JSON, deterministic validation (T-12 Approved), M-24 |
| P-07 | ML | Feature engineering | Dev B | Not Started | | Not Run | Strategy proposed in D-06 |
| P-08 | ML | Model training and evaluation | Dev B | Not Started | | Not Run | Seasonal Naive plus two variants (D-04, D-05) |
| P-09 | Crews | Data Scientist Crew | Dev B | Not Started | | Not Run | M-04 to M-06 |
| P-10 | Flow | CrewAI Flow orchestration | Shared | Not Started | | Not Run | Gates and states in [architecture.md](architecture.md) |
| P-11 | RAG | RAG knowledge base | Shared | Not Started | | Not Run | Optional, deferred (D-14, D-16) |
| P-12 | Agents | Business Recommendation Agent (Agent 7) | Shared | Not Started | | Not Run | Optional, deferred (D-16) |
| P-13 | App | Streamlit dashboard (A: data screens, B: forecasting screens) | Dev A / Dev B | Not Started | | Not Run | D-12 |
| P-14 | Storage | Supabase integration | Shared | Not Started | | Not Run | Optional, deferred (D-15); LocalRepository comes first (D-08) |
| P-15 | Testing | Unit and integration testing | Shared | Not Started | | Not Run | [testing-strategy.md](testing-strategy.md) |
| P-16 | Testing | End-to-end validation | Shared | Not Started | | Not Run | Also a phase gate, see [../CLAUDE.md](../CLAUDE.md) |
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
| `feature/data-inspection` | `dev` | Read-only M5 inspection; T-09 split and T-03 items (P-02) | In review | PR into `dev` |

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
| 2026-11-23 | Split (T-09) and product selection (T-03) approved; 20 `CA_1` items selected by deterministic stratified spread | PR pending |

## Current Blockers

| Blocker | Affects | Needed from |
|---|---|---|
| Open items (T-05 to T-10, T-13 to T-21) | Several tasks | Developers, see [decisions.md](decisions.md) |

## Next Actions

1. Michal accepts the Kaggle rules on her own account and downloads the files into `data/raw/` (git-ignored); the files are never shared (T-04 conditions).
2. Next data step (P-02): ETL wide-to-long for the 20 approved items, then validation and cleaning (P-03, null-price policy T-13). Model implementation and training wait (P-07, P-08).
3. Set a spend limit on the OpenAI project, create local `.env` files with `OPENAI_API_KEY`, then verify the model with one approved call (T-01).
4. Run the inspection yourself with `uv run python -m src.data.inspect_m5 --store-id CA_1`; it writes `artifacts/inspection/` (git-ignored).
5. Freeze the workstream interfaces in [agents-and-tasks.md](agents-and-tasks.md) at the end of week 1.

## Decision Log References

| Task | Depends on |
|---|---|
| P-02, P-03 | D-02, D-03, T-02, T-03, T-04, T-13 |
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
