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
| [architecture-plan.md](docs/architecture-plan.md) | The planning document these docs were generated from |

Original inputs kept for reference: [Word specification](docs/RetailAI_Project_Specification.docx), [instructor brief](docs/final_project_brief_1.html). Contributor and Claude Code conventions: [CLAUDE.md](CLAUDE.md).

## Setup and run

TBD (see decisions.md). Setup, environment and run commands will be added when the first code is merged (Python version and tooling are tracked in [decisions.md](docs/decisions.md)). Datasets are downloaded separately from Kaggle and are never committed. API keys go in a local `.env` file that is never committed.

## Limitations (planned)

One store and 20-50 items; M5 has no promotion or discount fields, so no causal claims; intermittent-demand items are harder to forecast; no inventory or cost data.
