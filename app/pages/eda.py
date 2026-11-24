"""Exploratory Data Analysis page (placeholder until step 4 of the data screens plan, P-13)."""

from __future__ import annotations

import streamlit as st

from app import common

st.title("Exploratory Data Analysis")
run = common.selected_run()
if run is not None:
    st.info(
        "Coming in the next step: the EDA report with its charts. Selected run: `"
        + run.run_id
        + "`."
    )
