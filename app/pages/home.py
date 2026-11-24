"""Home: what the system does, the data scope, and the status of the selected run."""

from __future__ import annotations

import streamlit as st

from app import common
from src.data.scope import ScopeError, load_scope
from src.repositories import run_artifacts as ra

PIPELINE = """
digraph {
  rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2f7", fontname="sans-serif"];
  raw [label="M5 files\\n(local, Kaggle)"];
  c1 [label="Crew 1: Data Analyst\\nValidator · Cleaner · Business Analyst"];
  g1 [label="Gate 1\\ncontract check", shape=diamond, fillcolor="#fff4d6"];
  c2 [label="Crew 2: Data Scientist\\n(next)", fillcolor="#f4f4f4"];
  g2 [label="Gate 2\\nforecast check", shape=diamond, fillcolor="#f4f4f4"];
  ui [label="This app"];
  raw -> c1 -> g1 -> c2 -> g2 -> ui; c1 -> ui [style=dashed];
}
"""
FILE_LABELS = {
    "quality_report.json": "Validation report",
    "clean_data.csv": "Clean data (not shown here: data rows stay local)",
    "cleaning_log.json": "Cleaning log",
    "eda_report.html": "EDA report",
    "eda_summary.json": "EDA facts",
    "insights.md": "Business insights",
    "dataset_contract.json": "Dataset contract",
    "contract_check.json": "Contract check (Gate 1 rules)",
}

st.title("RetailAI: sales intelligence")
st.write(
    "Multi-agent analysis and 28-day sales forecasting on the Kaggle M5 (Walmart) dataset. "
    "A team of AI agents validates and cleans the data, explains demand patterns and writes "
    "a data contract; a second team will train and evaluate the forecasting models. Every "
    "number on these pages comes from deterministic Python, not from the AI."
)
st.graphviz_chart(PIPELINE)

st.header("Data scope")
try:
    scope = load_scope()
except ScopeError as exc:
    st.error(f"The data scope cannot be read: {exc}")
else:
    groups = {g: sum(1 for v in scope.items.values() if v == g) for g in ("high", "medium", "low")}
    cols = st.columns(3)
    cols[0].metric("Store", scope.store_id)
    cols[1].metric("Products", len(scope.items))
    cols[2].metric("Forecast horizon", f"{scope.horizon_days} days")
    st.caption(
        f"Demand groups: {groups['high']} high, {groups['medium']} medium, {groups['low']} low "
        "(decision T-03). Split by day (T-09): "
        + "; ".join(f"{name} d_{r.first_day} to d_{r.last_day}" for name, r in scope.split.items())
        + ". Patterns and models use the training period only; the test period stays hidden."
    )

st.header("Selected run")
run = common.selected_run()
if run is not None:
    report = run.report
    if report is None:
        st.warning(
            "This run has no crew1_report.json: it is still running or stopped before the end."
        )
    else:
        status = report.get("status")
        (st.success if status == "completed" else st.error)(f"Crew 1 status: **{status}**")
        budget = report.get("llm_budget") or {}
        source = report.get("insights_source")
        cols = st.columns(3)
        cols[0].metric(
            "Insights written by",
            {"agent": "Business Analyst agent", "template": "Template (fallback)"}.get(
                source, "none"
            ),
        )
        cols[1].metric("LLM calls", f"{budget.get('calls', '?')} / {budget.get('max_calls', '?')}")
        cols[2].metric(
            "LLM tokens", f"{budget.get('tokens', 0):,} / {budget.get('max_tokens', 0):,}"
        )
        if report.get("fallback_reason"):
            st.info(f"Fallback reason: {report['fallback_reason']}")
        problems = report.get("problems") or []
        if problems:
            with st.expander(f"Problems recorded ({len(problems)})"):
                for p in problems:
                    st.write(f"- {p}")

    st.subheader("Crew 1 outputs")
    st.dataframe(
        [
            {"File": name, "What it is": FILE_LABELS[name], "Present": run.present[name]}
            for name in ra.CREW1_FILES
        ],
        hide_index=True,
        width="stretch",
    )

st.header("Run the pipeline")
st.write(
    "Runs are started from the command line for now; a button follows with the Flow (P-10). "
    "A run calls the OpenAI API and costs tokens, so start one only with the team's approval."
)
st.code(common.RUN_COMMAND, language="bash")
