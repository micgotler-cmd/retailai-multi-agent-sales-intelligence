"""Shared helpers for the Streamlit pages: the runs folder and the selected run.

Pages get run outputs only through src/repositories/run_artifacts.py (read-only,
never the data rows, T-04). The run picker lives in the sidebar of
streamlit_app.py and stores the chosen run id in the session state.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.repositories import run_artifacts as ra

RUNS_DIR_ENV = "RETAILAI_RUNS_DIR"  # optional; tests point it at a fixture folder
RUN_KEY = "run_id"
RUN_COMMAND = "uv run python -m src.crews.data_analyst_crew"


def runs_dir() -> Path:
    """The runs folder: RETAILAI_RUNS_DIR if set, else artifacts/runs."""
    return Path(os.environ.get(RUNS_DIR_ENV) or ra.DEFAULT_RUNS_DIR)


def run_label(run: ra.RunSummary) -> str:
    """How a run appears in the picker."""
    when = f"{run.started_at:%Y-%m-%d %H:%M} UTC" if run.started_at else run.run_id
    return f"{when} · {run.status}"


def selected_run() -> ra.RunArtifacts | None:
    """The run chosen in the sidebar, or None (with a message) if there is none."""
    run_id = st.session_state.get(RUN_KEY)
    if not run_id:
        no_runs_message()
        return None
    try:
        return ra.load_run(run_id, runs_dir())
    except ra.RunNotFound as exc:
        st.error(f"The selected run cannot be opened: {exc}")
        return None


def no_runs_message() -> None:
    st.info(
        "No pipeline run found yet. Run the Data Analyst Crew once (it calls the OpenAI API, "
        "so only with the team's approval), then reload this page:"
    )
    st.code(RUN_COMMAND, language="bash")


def missing_files_message(run: ra.RunArtifacts, names: list[str]) -> bool:
    """Show a warning for missing or unreadable files; True if all are usable."""
    missing = [n for n in names if not run.present.get(n, (run.path / n).is_file())]
    unreadable = {n: e for n, e in run.errors.items() if n in names}
    if missing:
        st.warning(f"This run has no {', '.join(missing)}. The run may have stopped early.")
    for name, error in unreadable.items():
        st.warning(f"{name} {error}.")
    return not missing and not unreadable
