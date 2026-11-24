"""Data Quality page (placeholder until step 3 of the data screens plan, P-13)."""

from __future__ import annotations

import streamlit as st

from app import common

st.title("Data Quality")
run = common.selected_run()
if run is not None:
    st.info(
        "Coming in the next step: the validation checks, cleaning actions, field summary and the Gate 1 contract rules. Selected run: `"
        + run.run_id
        + "`."
    )
