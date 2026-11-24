"""Business Insights page (placeholder until step 4 of the data screens plan, P-13)."""

from __future__ import annotations

import streamlit as st

from app import common

st.title("Business Insights")
run = common.selected_run()
if run is not None:
    st.info(
        "Coming in the next step: the insights, labeled agent or fallback, with charts from the EDA facts. Selected run: `"
        + run.run_id
        + "`."
    )
