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

Task status: Not Started, In Progress, Blocked, In Review, Completed. Test status: Not Run, Passed, Failed, Not Applicable. Owners are TBD until Developer A / B are assigned (T-11 in [decisions.md](decisions.md)).

| ID | Component | Task | Owner | Status | Branch / PR | Tests | Notes |
|---|---|---|---|---|---|---|---|
| P-01 | Setup | Repository and environment setup | TBD | In Review | `feature/env-setup` (PR into `dev`) | Not Applicable | Repo, branches and ruleset done. Python 3.12 environment, `pyproject.toml`, `uv.lock` in the PR; dependency audit run (D-24). Partner must run `uv sync` after merge; `.env` is created later (needs T-01) |
| P-02 | Data | M5 dataset ingestion | TBD | Not Started | | Not Run | Needs Kaggle download and usage-rights check (T-04); store and items TBD (T-02, T-03) |
| P-03 | Data | Data validation and cleaning | TBD | Not Started | | Not Run | Null-price policy TBD (T-13) |
| P-04 | Crews | Data Analyst Crew | TBD | Not Started | | Not Run | M-01 to M-03 |
| P-05 | Data | EDA and business insights | TBD | Not Started | | Not Run | M-02 |
| P-06 | Data | Dataset Contract | TBD | Not Started | | Not Run | Format TBD (T-12), M-24 |
| P-07 | ML | Feature engineering | TBD | Not Started | | Not Run | Strategy proposed in D-06 |
| P-08 | ML | Model training and evaluation | TBD | Not Started | | Not Run | Seasonal Naive plus two variants (D-04, D-05) |
| P-09 | Crews | Data Scientist Crew | TBD | Not Started | | Not Run | M-04 to M-06 |
| P-10 | Flow | CrewAI Flow orchestration | TBD | Not Started | | Not Run | Gates and states in [architecture.md](architecture.md) |
| P-11 | RAG | RAG knowledge base | TBD | Not Started | | Not Run | Optional, deferred (D-14, D-16) |
| P-12 | Agents | Business Recommendation Agent (Agent 7) | TBD | Not Started | | Not Run | Optional, deferred (D-16) |
| P-13 | App | Streamlit dashboard | TBD | Not Started | | Not Run | D-12 |
| P-14 | Storage | Supabase integration | TBD | Not Started | | Not Run | Optional, deferred (D-15); LocalRepository comes first (D-08) |
| P-15 | Testing | Unit and integration testing | TBD | Not Started | | Not Run | [testing-strategy.md](testing-strategy.md) |
| P-16 | Testing | End-to-end validation | TBD | Not Started | | Not Run | Also a phase gate, see [../CLAUDE.md](../CLAUDE.md) |
| P-17 | Delivery | Final presentation and demo | TBD | Not Started | | Not Applicable | 10-12 slides and a demo of at most 5 minutes (M-14) |

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

## Current Blockers

| Blocker | Affects | Needed from |
|---|---|---|
| Open items T-01 to T-20 | Several tasks | Developers, see [decisions.md](decisions.md) |

## Next Actions

1. Review and merge the env-setup PR; the other developer runs `uv sync`.
2. Resolve the Week 1 open items: T-01, T-02, T-03, T-04, T-11, T-12.
3. Each developer downloads M5 from Kaggle (never committed), then run the read-only dataset inspection (first implementation task, see [implementation-plan.md](implementation-plan.md)).
4. Each developer creates a local `.env` once T-01 is decided.

## Decision Log References

| Task | Depends on |
|---|---|
| P-02, P-03 | D-02, D-03, T-02, T-03, T-04, T-13 |
| P-06 | T-12 |
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
