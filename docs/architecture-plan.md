# Plan: RetailAI documentation system (docs only, no application code)

## Context
Before any implementation, we create a Markdown documentation set from Specification v1.3 (source of truth) and the instructor brief (`docs/final_project_brief_1.html`, binding for mandatory academic requirements). The Word spec and the brief stay in `docs/` untouched. No git repo, remote, package install or code is created in this step.

## Single-source rule (avoids duplication)
- `project-specification.md` owns **all requirements**, each with a stable ID (e.g. `REQ-M-01` mandatory, `REQ-O-03` optional) and a tag: Mandatory (brief) / Mandatory (MVP) / Optional enhancement.
- `decisions.md` owns **all decisions and every TBD**.
- Every other file describes *how*, links to requirement IDs and decisions instead of restating them.

## Proposed files
| File | Purpose / contents |
|---|---|
| `README.md` | What RetailAI is (3-4 lines), status, quick links to docs, setup/run section (marked TBD until code exists), artifacts list, limitations. No requirement detail. |
| `CLAUDE.md` | Concise: project context, the 2 crews x 3 agents + Agent 7 rule, coding conventions (Python 3.12 TBD, type hints, ruff, pytest, deterministic code does numerics, LLM agents only reason/orchestrate), dev rules (small tasks, tests first, no secrets, no committing data/.env/vector DB, planning before code, branch + PR workflow), testing expectations, doc map with links. |
| `docs/project-specification.md` | Faithful Markdown conversion of the Word spec v1.3, all 19 sections preserved, with requirement IDs and a Mandatory/Optional status column. Includes the brief's mandatory list as a short compliance table. Differences from the spec are listed in one "Corrections" section: `store_nbr`/`family` in the DB schema replaced by `store_id`/`item_id` (per your instruction), the Hebrew test row translated to English. |
| `docs/architecture.md` | System overview, Mermaid flowchart (exactly Crew 1: Validator, Cleaner, Business Analyst; Crew 2: Feature Engineer, Model Trainer, Model Evaluator; Agent 7 independent, after the Forecast Validation Gate), Flow states and validation gates (state diagram), failure handling (RAG/Supabase failure never invalidates the forecast), proposed repository layout, config/logging/reproducibility. |
| `docs/agents-and-tasks.md` | Table per agent: role, inputs, outputs, deterministic tools, forbidden actions (Agent 7 cannot train/modify data/activate promotions). Task list per crew, handoff contracts between crews and to Agent 7. |
| `docs/data-and-ml.md` | M5 files and ETL (wide to long), 20-50 items / one store subset rule (TBD values), dataset contract fields, 28-day product-level forecasting, chronological splits, leakage rules, Seasonal Naive + two sklearn models, MAE/RMSE, multi-step strategy (marked **Proposed**), price handling, promotions as optional descriptive analysis only. |
| `docs/rag-and-recommendations.md` | Agent 7 scope, synthetic policy documents and metadata, chunking/embedding/retrieval (CrewAI Knowledge vs local Chroma = TBD after compatibility check), citation verification, abstention, prompt-injection protections, `recommendation.json` schema, RAG test set and acceptance, 4-6 h timebox. |
| `docs/database-design.md` | Repository abstraction (`LocalRepository`, `SupabaseRepository`, methods from spec), schema for `analysis_runs`, `sales_predictions` (`store_id`, `item_id`), `business_insights`, recommendation storage options (TBD), constraints, idempotent writes, security, migrations, local fallback. Marked planned/optional. |
| `docs/implementation-plan.md` | Four-week plan for two developers: objectives, tasks, dependencies, deliverables, exit criteria, ownership (Dev A / Dev B from spec section 15), MVP milestone, deferral order, Claude Code workflow (small reviewed tasks). |
| `docs/testing-strategy.md` | Test layers (unit, data validation, contract, feature/leakage, model evaluation, Flow integration, RAG, Supabase, Streamlit smoke, e2e) with positive/negative cases and measurable acceptance criteria, linking to spec section 13. |
| `docs/decisions.md` | Decision log table: ID, decision, status (**Proposed / Approved / Deferred**), rationale, link. Plus the full list of TBD items. |

## Decision statuses (initial draft)
- Approved (from spec/brief/your messages): 2 crews x 3 agents + Agent 7; M5 dataset planned; 28-day product-level horizon; Seasonal Naive + 2 sklearn models; LocalRepository first; app works without Supabase; schema uses `store_id`/`item_id`.
- Proposed: direct forecasting with lags >= 28 days, price excluded from MVP model; Python 3.12 via uv; SQLite as local repository store; separate `recommendations` table; Streamlit as the UI.
- Deferred: Supabase connection (week 3+), Agent 7/RAG build (after MVP gate), cloud deployment.
- TBD: LLM/embedding provider, MVP store (default CA_1 proposed), item subset size, Supabase project, second developer's GitHub username, whether to commit final artifacts, instructor confirmation on extensions.

## Rules applied while writing
Mermaid in architecture, data flow and the implementation timeline; every internal link relative and checked by a script at the end (all `[..](path)` targets exist, anchors verified); nothing invented: unknowns are `TBD`; each file kept short (target 1-3 pages, spec conversion longest).

## Verification (after approval and generation)
1. Run a link checker over all `.md` files (relative paths and heading anchors).
2. Grep for requirement IDs used in other files and confirm each exists in `project-specification.md`.
3. Confirm the diagram shows exactly 3+3 agents plus Agent 7.
4. Confirm every TBD in any file appears in `decisions.md`.
5. Confirm both original files are untouched in `docs/`.

## Scope confirmed by user: create ONLY the .md files
Exactly 11 files: `README.md`, `CLAUDE.md` at the root and the 9 files under `docs/`. No other files or folders (no `.gitignore`, no `src/`, no `.env.example`), no helper scripts left behind. The link check runs inline and writes nothing.

## Out of scope for this step
Git init, GitHub repo creation, environment setup, any application code.
