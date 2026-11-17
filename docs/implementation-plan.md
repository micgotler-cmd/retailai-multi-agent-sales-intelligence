# Implementation Plan

Four weeks, two developers. Schedule source: section 16 of [project-specification.md](project-specification.md). Ownership: Developer A (Crew 1, data views), Developer B (Crew 2, forecasting views); who is who is TBD (T-11). Open choices: [decisions.md](decisions.md).

**Priority order:** 1. mandatory academic requirements, 2. working end-to-end forecasting, 3. Agent 7 and RAG, 4. Supabase, 5. optional improvements. **MVP milestone:** end of week 3, a local end-to-end run (both crews, both gates, Streamlit) with no RAG and no Supabase.

```mermaid
gantt
    dateFormat  YYYY-MM-DD
    axisFormat  Week %W
    section Foundation
    Env, repo, data inspection, contract, PoC     :w1, 2026-01-05, 7d
    section Core
    Both crews, two models, artifacts             :w2, after w1, 7d
    Flow, gates, Streamlit, integration tests     :w3, after w2, 7d
    section Extensions and delivery
    Agent 7 and RAG (timebox), Supabase if on track :after w3, 4d
    QA, docs, slides, demo                         :w4, after w3, 7d
```

Dates in the chart are placeholders only; actual start date is TBD (T-19).

## Week 1: foundation

| | |
|---|---|
| Objective | Repository and environment ready; data inspected; baseline works |
| Dev A | Download M5 (T-04), inspect files, ETL wide-to-long, choose store and items (T-02, T-03), draft contract (T-12), start Crew 1 tools |
| Dev B | Python 3.12 environment (D-13), feature and baseline PoC (Seasonal Naive plus Ridge), `Repository` interface and `LocalRepository` |
| Both | Confirm open items T-01, T-02, T-03, T-09 |
| Deliverables | Clean long-format data, draft contract, working baseline, repo with CI skeleton |
| Exit | Clean data and a working baseline |
| Effort | About 12-15 h per developer |

## Week 2: crews and models

| | |
|---|---|
| Objective | Both crews work independently and produce all eight artifacts |
| Dev A | Crew 1 agents and tasks, `eda_report.html`, `insights.md`, `dataset_contract.json` |
| Dev B | Crew 2 agents and tasks, Ridge and Random Forest, per-item MAE/RMSE, `model_card.md` |
| Dependency | Dev B consumes the contract and `clean_data.csv` format agreed in week 1 |
| Exit | Each crew runs on its own and writes its artifacts |

## Week 3: Flow, UI, integration (MVP gate)

| | |
|---|---|
| Objective | End-to-end execution with validation and graceful failure |
| Dev A | Streamlit screens (Home, Data Quality, EDA, Insights, Run History) |
| Dev B | CrewAI Flow, Gate 1 and Gate 2, logging, Forecast and Model Evaluation screens, Flow integration tests |
| Then | Agent 7 and RAG in a 4-6 h timebox (D-16) if the MVP gate is met; Supabase only after that (D-15) |
| Exit | One command runs the full local pipeline and the UI shows its results |

## Week 4: QA and delivery

| | |
|---|---|
| Objective | Stable submission package |
| Tasks | Bug fixes, end-to-end and failure tests, README setup and reproduction check on a clean machine, 10-12 slide presentation, demo video of at most 5 minutes (M-14), decision on committing final artifacts (T-07) |
| Optional | Supabase adapter and migrations; deployment (D-17) |
| Exit | Submission package complete; each developer has a documented merged PR (M-12) |

## What can run in parallel

- ETL and contract (A) with features and models (B), once the contract and `clean_data.csv` format are frozen.
- Streamlit pages (A/B) with Flow work, once artifact formats are frozen.
- Repository interface (B, week 1) with everything else.

**If late, cut in this order:** Supabase, then Agent 7/RAG, then promotions analysis. Never cut the mandatory Flow, artifacts or forecasts.

## Working with Claude Code

One focused task at a time, each ending in a reviewed pull request:

1. State the task, the files involved, and the expected output.
2. Write or update tests first, then the code.
3. Run tests locally; both developers can explain the diff.
4. Run a code review, then merge via PR before starting the next task.

Suggested task order: environment and scaffold, config and logging, data inspection, ETL and validation, contract, features with leakage tests, models and evaluation, tool wrappers, Crew 1, Crew 2, Flow and gates, LocalRepository, Streamlit pages, then the optional parts. Do not generate the whole application in one step. Conventions: [../CLAUDE.md](../CLAUDE.md).

## Git workflow (D-18, D-19)

`main` is the default and protected branch; short-lived `feature/<area>-<description>` branches; one PR per task, reviewed by the other developer; squash merge. Repository `retailai-multi-agent-sales-intelligence`, private initially. The remote repository is created only after explicit approval; GitHub CLI is already authenticated.

**Branch names:** `feature/data-ingestion`, `feature/analyst-crew`, `feature/ml-forecasting`, `feature/rag-recommendations`, `feature/supabase-integration`, `docs/update-architecture`. Small focused commits; PR descriptions say what changed, how it was tested and which `docs/progress.md` rows were updated; no merge without the other developer's review.

**Second developer (after being invited, T-06):**
```
git clone https://github.com/<owner>/retailai-multi-agent-sales-intelligence.git
cd retailai-multi-agent-sales-intelligence
git checkout -b feature/<task>      # work, commit, then:
git push -u origin feature/<task>   # open a Pull Request into main
```
Copy `.env.example` to `.env` locally and fill in your own keys; never commit `.env`.

## Recommended first implementation task

A read-only dataset inspection script that reports shape, date range, missing dates, price coverage and zero rate per item, and proposes the store and item subset. This validates feasibility before any crew is written (informs T-02, T-03, T-09).
