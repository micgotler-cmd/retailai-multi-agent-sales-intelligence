"""RetailAI Streamlit app: navigation and the run picker (P-13, D-12).

Start it from the repository root:
    uv run streamlit run app/streamlit_app.py

The pages only read the outputs of finished runs in artifacts/runs/; nothing
here starts a run or calls an LLM (a run button comes with the Flow, P-10).
Dev B's forecasting pages are added to PAGES under "Forecasting".
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `streamlit run` puts only app/ on the path
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app import common
from src.repositories import run_artifacts as ra

PAGES = {
    "Overview": [
        st.Page("pages/home.py", title="Home", icon=":material/home:", default=True),
    ],
    "Data": [
        st.Page("pages/data_quality.py", title="Data Quality", icon=":material/fact_check:"),
        st.Page("pages/eda.py", title="Exploratory Data Analysis", icon=":material/bar_chart:"),
        st.Page("pages/insights.py", title="Business Insights", icon=":material/lightbulb:"),
    ],
}


PICKER_KEY = "_run_picker"


def _remember_choice() -> None:
    st.session_state[common.RUN_KEY] = st.session_state[PICKER_KEY]


def run_picker() -> None:
    """Sidebar select box of the runs; defaults to the newest completed run."""
    runs = ra.list_runs(common.runs_dir())
    if not runs:
        st.session_state[common.RUN_KEY] = None
        st.sidebar.caption("No runs yet")
        return
    ids = [r.run_id for r in runs]
    labels = {r.run_id: common.run_label(r) for r in runs}
    if st.session_state.get(common.RUN_KEY) not in ids:  # first visit, or the run was removed
        st.session_state[common.RUN_KEY] = (ra.latest_completed(runs) or runs[0]).run_id
    # The choice lives in its own key, copied from the widget on change, so it survives
    # page changes and reruns (Streamlit's pattern for values shared by pages).
    st.session_state[PICKER_KEY] = st.session_state[common.RUN_KEY]
    st.sidebar.selectbox(
        "Pipeline run", ids, key=PICKER_KEY, format_func=labels.get, on_change=_remember_choice
    )
    st.sidebar.caption(f"Run id: `{st.session_state[common.RUN_KEY]}`")


st.set_page_config(page_title="RetailAI", page_icon=":material/storefront:", layout="wide")
run_picker()
st.navigation(PAGES).run()
