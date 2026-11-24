"""Data Quality: validation results, cleaning actions, field summary and the Gate 1 rules.

Shows only the reports written by the deterministic tools (aggregates and
counts), never data rows (T-04).
"""

from __future__ import annotations

import streamlit as st

from app import common, tables

FILES = ["quality_report.json", "cleaning_log.json", "dataset_contract.json", "contract_check.json"]

st.title("Data Quality")
run = common.selected_run()
if run is not None:
    st.caption(
        "Results of Agent 1 (Data Validator) and Agent 2 (Data Cleaner). Every check and count "
        "was computed by deterministic Python; no data rows are shown."
    )
    quality, log, contract, check = (run.json(name) for name in FILES)
    common.missing_files_message(run, FILES)  # after reading, so broken files are listed too

    # ------------------------------------------------------------ validation
    st.header("1. Validation of the raw M5 files")
    if quality is not None:
        summary = quality.get("summary") or {}
        status = quality.get("status")
        (st.success if status == "pass" else st.error)(
            f"Validation status: **{status}**. Store {quality.get('store_id', '?')}, "
            f"{quality.get('items_in_scope', '?')} products in scope."
        )
        cols = st.columns(4)
        cols[0].metric("Checks", summary.get("checks", "?"))
        cols[1].metric("Passed", summary.get("passed", "?"))
        cols[2].metric("Warnings", summary.get("warnings", "?"))
        cols[3].metric("Failed", summary.get("failed", "?"))
        st.dataframe(tables.check_rows(quality), hide_index=True, width="stretch")
        if summary.get("blocking_failures"):
            st.error("Blocking failures: " + ", ".join(summary["blocking_failures"]))

    # -------------------------------------------------------------- cleaning
    st.header("2. Cleaning (rules T-13)")
    if log is not None:
        rows_in, rows_out = log.get("rows_in"), log.get("rows_out")
        cols = st.columns(3)
        cols[0].metric("Rows in", f"{rows_in:,}" if isinstance(rows_in, int) else "?")
        cols[1].metric("Rows out", f"{rows_out:,}" if isinstance(rows_out, int) else "?")
        cols[2].metric("Period", f"{log.get('first_date', '?')} to {log.get('last_date', '?')}")
        st.dataframe(tables.action_rows(log), hide_index=True, width="stretch")
        with st.expander("First sale and rows dropped per product"):
            st.dataframe(tables.first_sale_rows(log), hide_index=True, width="stretch")

    # ------------------------------------------------------- field summary
    st.header("3. Fields and missing values (dataset contract)")
    if contract is not None:
        granularity = contract.get("granularity") or {}
        if granularity.get("row"):
            st.write(
                f"One row is **{granularity['row']}**, {granularity.get('per_item_range', '')}."
            )
        st.dataframe(tables.field_rows(contract), hide_index=True, width="stretch")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Assumptions")
            for item in contract.get("assumptions") or []:
                st.write(f"- {item}")
        with col2:
            st.subheader("Limitations")
            for item in contract.get("limitations") or []:
                st.write(f"- {item}")

    # ---------------------------------------------------------- Gate 1
    st.header("4. Gate 1: clean data against the contract")
    if check is not None:
        status = check.get("status")
        (st.success if status == "pass" else st.error)(
            f"Contract check: **{status}**. The Data Scientist Crew may use this data only if "
            "every rule passes."
        )
        st.dataframe(tables.check_rows(check), hide_index=True, width="stretch")
        if check.get("failed_rules"):
            st.error("Failed rules: " + ", ".join(check["failed_rules"]))
