# CLAUDE.md

Guidance for Claude Code in this repository. Keep this file short; details live in the docs linked below.

## Project

RetailAI: multi-agent sales intelligence on the Kaggle M5 dataset (Python, CrewAI, Streamlit). Two developers, four weeks. Two CrewAI crews of exactly three agents each, coordinated by a CrewAI Flow, plus an independent seventh Business Recommendation Agent that runs once after a validated forecast. Forecast: 28 days, per `item_id` x `store_id`. RAG (Agent 7) and Supabase are optional, time-boxed enhancements.

## Source of truth

- Requirements: [docs/project-specification.md](docs/project-specification.md) (IDs `M-xx` mandatory, `O-xx` optional). Do not invent or change requirements.
- Decisions and open items: [docs/decisions.md](docs/decisions.md). Anything marked `TBD` or Proposed must be confirmed with the developers before it is built as fact.
- Design: [architecture.md](docs/architecture.md), [agents-and-tasks.md](docs/agents-and-tasks.md), [data-and-ml.md](docs/data-and-ml.md), [rag-and-recommendations.md](docs/rag-and-recommendations.md), [database-design.md](docs/database-design.md).
- Plan and tests: [implementation-plan.md](docs/implementation-plan.md), [testing-strategy.md](docs/testing-strategy.md).

Do not duplicate requirements in other files; link to them.

## Development rules

- Work on one small, focused task at a time. Describe the plan first; wait for approval before large changes. Never generate the whole application at once.
- Mandatory work first: Flow, both crews, eight artifacts, forecasts. Agent 7/RAG, then Supabase, only after the MVP gate.
- Deterministic Python tools do all numeric work (ETL, features, training, metrics, citation checks). LLM agents reason, orchestrate and explain; they never compute metrics or edit data themselves.
- Never assume a dataset field exists; check the real files. M5 has no promotion or discount field.
- Prevent leakage: chronological splits only, test data never used for training or tuning, no unknown future features.
- The pipeline must run without Supabase and without RAG. A RAG or Supabase failure never invalidates a validated forecast.
- Never fabricate citations, metrics or policies. Demo policies are labeled synthetic.
- Never commit `.env`, credentials, datasets, local vector indexes or large generated artifacts. Never print secrets or put them in logs. Do not execute LLM-generated code without review.
- **Phase gate:** at every transition from one development phase to the next, run (1) a security review (for example the `security-review` skill) and (2) the end-to-end test for everything built so far (see [docs/testing-strategy.md](docs/testing-strategy.md)). Do not start the next phase until both have passed; fix findings first and re-run.
- Get approval before major architectural changes (anything listed in [docs/decisions.md](docs/decisions.md)); record the outcome there.
- Ask before installing packages, creating remote resources, or running destructive commands.
- Use the `store_id` / `item_id` naming everywhere (not `store_nbr` / `family`).

## Coding conventions

- Python (3.12 proposed, D-13 in decisions), type hints, small functions, docstrings for public functions.
- Crew and agent files contain definitions only; logic lives in `src/data`, `src/ml`, `src/rag`, `src/repositories` and is exposed to agents through thin typed tools (layout: [docs/architecture.md](docs/architecture.md)).
- Config via environment variables and one config module; fixed random seeds; log every Flow state transition and gate result.
- Format and lint with ruff (planned); keep dependencies pinned.

## Testing expectations

- Every change ships with tests, including at least one failure case. Use small fixture data and mocked LLM calls.
- Run the test suite before opening a pull request. Layers and acceptance criteria: [docs/testing-strategy.md](docs/testing-strategy.md).

## Git workflow

Two permanent branches (D-23): `main` is production and the default branch; `dev` is the integration branch.
- Never commit directly to `main` (or `dev`); work on a feature branch created from `dev` (`feature/<task>`, `docs/<topic>`).
- Open PRs into `dev`; `dev` goes into `main` by PR at a stable milestone, only after the phase gate above has passed and the other developer has approved.
- Update `docs/progress.md` in the same PR, and keep `docs/project-plan-simple.html` (plain-language overview) in step with project progress. Small, focused commits and clear PR descriptions.
- Do not create or change remote branches, branch protection or deployments without approval.

Details: [docs/implementation-plan.md](docs/implementation-plan.md). Progress is tracked in [docs/progress.md](docs/progress.md); update it in the relevant PR.
