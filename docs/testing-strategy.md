# Testing Strategy

Practical tests for a two-developer, four-week project. Acceptance scenarios from section 13 of [project-specification.md](project-specification.md). Design under test: [architecture.md](architecture.md), [data-and-ml.md](data-and-ml.md).

## Principles

- Tests use a small fixture dataset (about 3 items, around 200 days, M5-shaped) committed under `tests/`; no real M5 data and no network.
- LLM calls are mocked in automated tests. Numeric logic is tested directly because it is deterministic.
- Optional layers (Supabase, RAG) are skipped automatically when their configuration is missing, and never block the mandatory suite.
- Tests run locally and in CI on every pull request (pytest, ruff).

## Test layers

| Layer | Positive cases | Negative / failure cases | Acceptance criterion |
|---|---|---|---|
| Unit (config, logging, helpers) | Config loads defaults; log redacts secrets | Missing env value gives a clear error | All pass |
| Data validation | Fixture passes schema, null, duplicate, range checks | Missing column, negative `units_sold`, duplicate keys, null `store_id` | Readable error; Crew 2 never starts (M-19) |
| Dataset contract | Contract matches `clean_data.csv` | Wrong type, out-of-range value, unknown column | Controlled failure at Gate 1, logged (M-08) |
| ETL | Wide-to-long row count equals items x days; calendar and price joins correct | Missing price weeks handled per documented policy | Row counts and keys verified |
| Feature engineering | Lags and rolling values equal hand-computed values | A feature using data newer than the forecast origin is detected | Leakage test passes; all required features present |
| Model evaluation | MAE/RMSE match hand computation on a tiny case; final metrics use the test holdout; each backtest window's fit uses only data up to its origin; Seasonal Naive equals the last 7 days repeated | Random split, test rows in training or a fit that sees data after its origin detected | Seasonal Naive plus two models reported overall and per item (M-16, M-17) |
| Reproducibility | Same seed and inputs give identical metrics | Seed missing from the manifest | Identical results across two runs (M-20) |
| Flow integration | Fixture run produces all eight artifacts | Gate failure stops the Flow with status FAILED; Crew 2 not started | States and logs as designed (M-07, M-10) |
| RAG retrieval and citations (optional) | Section retrieval returns the expected `source_id` | No-source case, conflicting policy, irrelevant document, injection text in a document | At least 8 of 10 correct source or abstention; zero fabricated references |
| Agent 7 output checks (optional) | Valid `recommendation.json` | Unknown `source_id`, quote not in source, unsupported discount percentage, wrong `run_id` | Rejected; status `insufficient_evidence` |
| RAG failure (optional) | | Index missing or retrieval error | Forecast still available; UI shows "Knowledge-grounded recommendation unavailable" |
| Repository contract | Same suite passes on `LocalRepository` and `SupabaseRepository` | Retry writes no duplicates; Supabase unreachable | Consistent behavior; local artifacts intact (spec s10A tests 1-5) |
| Secrets | | Scan source and logs for key patterns | None found (spec s10A test 6) |
| Streamlit smoke | Each page loads with fixture artifacts (`streamlit.testing.v1.AppTest`) | Missing artifacts give a message, not an exception | No uncaught exception |
| End to end | Real run on the chosen 20-50 items completes and writes eight artifacts | Corrupt input file fails gracefully | Reproducible metrics with the same seed |

## Spec scenario mapping

| Spec scenario | Covered by |
|---|---|
| Valid CSV: eight artifacts | Flow integration, end to end |
| Missing required field | Data validation |
| Invalid contract value | Dataset contract |
| Evaluation on held-out chronological data | Model evaluation |
| Repeated execution reproducible | Reproducibility |
| RAG retrieval failure | RAG failure |
| GitHub PR and README reproduction | Manual check in week 4 (M-12, M-15) |
| Agent 7 without supporting policy | Agent 7 output checks |

## RAG test set (optional layer)

8-12 questions, each with an expected `source_id` or an expected abstention. Required coverage: policy section retrieval, no-source question, conflicting or outdated policy, irrelevant document, injection attempt embedded in a document. Case list is written when D-16 starts. See [rag-and-recommendations.md](rag-and-recommendations.md).

## Quality gates for a pull request

- Tests and lint pass in CI.
- New behavior has a test, including at least one failure case.
- The other developer reviews and can explain the change.
- No datasets, `.env` files, credentials, vector indexes or large artifacts in the diff.
