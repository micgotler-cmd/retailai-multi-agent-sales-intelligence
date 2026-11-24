# RetailAI: Multi-Agent Sales Intelligence

Final project for an AI Developers course (two developers, four weeks). RetailAI analyzes historical retail sales, produces business insights, and forecasts product-level demand for the next 28 days using the Kaggle M5 (Walmart) dataset. It is built with Python and CrewAI: two crews of three agents each, coordinated by a CrewAI Flow, plus an optional independent Business Recommendation Agent that uses RAG after forecasting.

**Status:** planning complete; no application code yet. See [implementation-plan.md](docs/implementation-plan.md).

## What it produces

| Crew | Artifacts |
|---|---|
| Data Analyst | `clean_data.csv`, `eda_report.html`, `insights.md`, `dataset_contract.json` |
| Data Scientist | `features.csv`, `model.joblib` (or `.pkl`), `evaluation_report.md`, `model_card.md` |
| Business Recommendation Agent (optional) | `recommendation.json` |

A Streamlit app shows data quality, EDA, insights, forecasts, model evaluation, recommendations and run history. Supabase persistence is planned and optional; the app works fully without it.

## Documentation

| Document | Content |
|---|---|
| [project-specification.md](docs/project-specification.md) | All requirements (mandatory vs optional), source of truth |
| [architecture.md](docs/architecture.md) | System design, Flow, gates, diagrams, repository layout |
| [agents-and-tasks.md](docs/agents-and-tasks.md) | The seven agents, tasks and handoffs |
| [data-and-ml.md](docs/data-and-ml.md) | M5 dataset, ETL, 28-day forecasting, evaluation |
| [rag-and-recommendations.md](docs/rag-and-recommendations.md) | Agent 7 and RAG design (optional) |
| [database-design.md](docs/database-design.md) | Repository abstraction and Supabase schema (optional) |
| [implementation-plan.md](docs/implementation-plan.md) | Four-week plan and workflow |
| [testing-strategy.md](docs/testing-strategy.md) | Test layers and acceptance criteria |
| [decisions.md](docs/decisions.md) | Decision log and open items (TBD) |
| [progress.md](docs/progress.md) | Shared progress tracker |
| [project-plan-simple.html](docs/project-plan-simple.html) | The whole plan in simple words (open in a browser) |
| [architecture-plan.md](docs/architecture-plan.md) | The planning document these docs were generated from |

Original inputs kept for reference: [Word specification](docs/RetailAI_Project_Specification.docx), [instructor brief](docs/final_project_brief_1.html). Contributor and Claude Code conventions: [CLAUDE.md](CLAUDE.md).

## Branching strategy

| Branch | Purpose |
|---|---|
| `main` | Stable, production-ready version; GitHub default branch. Changes arrive only by Pull Request from `dev` |
| `dev` | Shared integration and testing branch; all new work starts here |
| `feature/<task>`, `docs/<topic>` | Short-lived branches created from `dev`, merged back into `dev` by Pull Request |

Flow: branch from `dev`, implement and test, update [docs/progress.md](docs/progress.md), open a PR into `dev`, get review, merge. At a stable milestone, open a PR from `dev` into `main` after final validation. Details: [implementation-plan.md](docs/implementation-plan.md) and decision D-23 in [decisions.md](docs/decisions.md).

## Setup and run

Requires [uv](https://docs.astral.sh/uv/) (`brew install uv`). Python 3.12 is used (pinned in `.python-version`); your system Python is not touched.

```
git clone https://github.com/micgotler-cmd/retailai-multi-agent-sales-intelligence.git
cd retailai-multi-agent-sales-intelligence
git checkout dev
uv python install 3.12     # once
uv sync                    # creates .venv and installs the locked versions from uv.lock
uv run pytest              # runs the tests (no API calls; the LLM is mocked)
```

- Run commands inside the environment with `uv run <command>` (or activate `.venv`).
- Data: see [Data source](#data-source) below. Datasets are never committed.
- The OpenAI API key goes in a local `.env` (copy `.env.example`; needed once the code calls an LLM). `.env` is never committed.
- Data steps only (no LLM): `uv run python -m src.data.cleaning`, then `uv run python -m src.data.contract`.
- Crew 1, the Data Analyst Crew (calls the OpenAI API, costs tokens; only with the team's approval): `uv run python -m src.crews.data_analyst_crew`. Outputs go to `artifacts/runs/<run_id>/`.
- The app: `uv run streamlit run app/streamlit_app.py`, then open <http://localhost:8501>. It only reads finished runs; it serves on this computer only and Streamlit usage statistics are off (`.streamlit/config.toml`).

## Data source

Kaggle [M5 Forecasting - Accuracy](https://www.kaggle.com/competitions/m5-forecasting-accuracy) (Walmart sales data). The data is subject to the competition rules, which allow non-commercial use for academic research and education and forbid redistribution to anyone who has not accepted them (decision T-04 in [docs/decisions.md](docs/decisions.md)). This repository therefore contains no M5 data. To run the project:

1. Sign in to Kaggle, open the competition, read the Rules and accept them with your own account.
2. Download the files from the Data tab and unzip them into `data/raw/` at the repository root (Git ignores this folder).
3. Do not share the files with anyone; each person downloads their own copy.

## Limitations (planned)

One store and 20-50 items; M5 has no promotion or discount fields, so no causal claims; intermittent-demand items are harder to forecast; no inventory or cost data.
