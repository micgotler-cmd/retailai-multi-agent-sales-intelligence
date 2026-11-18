# Progress Tracker

Shared development tracker for RetailAI. Requirements: [project-specification.md](project-specification.md). Decisions and open items: [decisions.md](decisions.md). Plan: [implementation-plan.md](implementation-plan.md).

## Project Status

| Field | Value |
|---|---|
| Project name | RetailAI: Multi-Agent Sales Intelligence |
| Current phase | Phase 0: repository and documentation setup (no application code yet) |
| Overall status | On track; documentation set created, remote repository pending approval |
| Last updated | 2026-11-17 |
| Next milestone | Week 1 exit: clean data and a working baseline ([implementation-plan.md](implementation-plan.md)) |

## Development Progress

Task status: Not Started, In Progress, Blocked, In Review, Completed. Test status: Not Run, Passed, Failed, Not Applicable. Owners show the responsibility role (Dev A, Dev B, Shared) from T-11; which person is A or B is still pending ([decisions.md](decisions.md)).

| ID | Component | Task | Owner | Status | Branch / PR | Tests | Notes |
|---|---|---|---|---|---|---|---|
| P-01 | Setup | Repository and environment setup | Shared | In Review | `feature/env-setup` (PR into `dev`) | Not Applicable | Repo, branches and ruleset done. Python 3.12 environment, `pyproject.toml`, `uv.lock` in the PR; dependency audit run (D-24). Partner must run `uv sync` after merge; `.env` is created later (needs T-01) |
| P-02 | Data | M5 dataset ingestion | Dev A | Not Started | | Not Run | Blocked on the Kaggle terms check (T-04, pending). Store is `CA_1` (T-02); 20 items chosen by the T-03 method after inspection |
| P-03 | Data | Data validation and cleaning | Dev A | Not Started | | Not Run | Null-price policy TBD (T-13) |
| P-04 | Crews | Data Analyst Crew | Dev A | Not Started | | Not Run | M-01 to M-03 |
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
| `feature/env-setup` | `dev` | Python 3.12 environment with uv (D-13) | In review | PR into `dev` |

Add one row per feature branch and its PR (target `dev`) as work starts.

## Completed Work

| Date | Milestone | PR |
|---|---|---|
| 2026-11-17 | Documentation set created (README, CLAUDE.md, 10 documents under `docs/`) and internal links checked | Initial commit `82aeec9` on `main` (no PR) |
| 2026-11-17 | Public GitHub repository created and `main` pushed | n/a |
| 2026-11-17 | `dev` branch created, ruleset for `main` and `dev` enabled, branching strategy documented (D-23) | #1, #2 |
| 2026-11-18 | Second developer is a collaborator and has cloned the repository | n/a |
| 2026-11-18 | Simple-language plan overview added to `dev` and `main` | #3, #4 |
| 2026-11-18 | Planning decisions recorded: T-11 (responsibilities), T-01 (OpenAI provider), T-02 (`CA_1`), T-03 (approach), T-12 (JSON contract); T-04 pending. Documentation only; no development task is complete | PR pending |

## Current Blockers

| Blocker | Affects | Needed from |
|---|---|---|
| Kaggle M5 terms not yet verified (T-04) | P-02 and everything after it | A developer with a Kaggle login |
| Open items (T-05 to T-10, T-13 to T-21) | Several tasks | Developers, see [decisions.md](decisions.md) |

## Next Actions

1. Check and record the Kaggle M5 terms (T-04), then each developer downloads the three files into `data/raw/` (git-ignored).
2. Confirm who is Developer A and who is B (T-11).
3. Set a spend limit on the OpenAI project, create local `.env` files with `OPENAI_API_KEY`, then verify the model with one approved call (T-01).
4. Run the read-only dataset inspection (first implementation task, see [implementation-plan.md](implementation-plan.md)); it settles the item thresholds (T-03) and split dates (T-09).
5. Freeze the workstream interfaces in [agents-and-tasks.md](agents-and-tasks.md) at the end of week 1.

## Decision Log References

| Task | Depends on |
|---|---|
| P-02, P-03 | D-02, D-03, T-02, T-03, T-04, T-13 |
| P-04 to P-10 | T-01 (OpenAI), T-11 |
| P-06 | T-12 (Approved) |
| P-07, P-08 | D-04 to D-07, T-09, T-16 |
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
