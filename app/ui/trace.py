"""Shared Trace UI pieces: sidebar (user, brain status, reset), source chips, status badges."""

import time

import streamlit as st

from app.config import settings
from app.core import changes, decisions, indexer
from app.core.models import SourceRef
from app.data import workspace

STATUS = {
    "held": ("red", "HELD"),
    "proposed": ("green", "READY"),
    "accepted": ("gray", "ENTERED"),
    "rejected": ("gray", "REJECTED"),
}


def user() -> str:
    return st.session_state.get("trace_user", settings.trace_user)


def setup() -> None:
    """Call at the top of every Trace page."""
    workspace.ensure()


def sidebar() -> None:
    with st.sidebar:
        people = list(workspace.users())
        default = people.index(settings.trace_user) if settings.trace_user in people else 0
        st.selectbox("Working as", people, key="trace_user", index=default)

        # BRAIN STATUS
        st.divider()
        st.subheader("Brain Status")

        files = indexer.load()
        css = changes.all_changesets()
        all_decisions = decisions.all_decisions()

        held = sum(cs.status == "held" for cs in css)
        ready = sum(cs.status == "proposed" for cs in css)
        entered = sum(cs.status == "accepted" for cs in css)
        new_files = sum(f.status == "new" for f in files)

        col1, col2 = st.columns(2)
        col1.metric("Files", len(files), f"{new_files} new")
        col2.metric("Open", held, f"{ready} ready")

        col1, col2 = st.columns(2)
        col1.metric("Entered", entered, None)
        col2.metric("Decisions", len(all_decisions), None)

        # Last commit
        last = workspace.git(
            "log", "-1", "--format=%h|%an|%ad", "--date=short", check=False
        ).strip()
        if last:
            parts = last.split("|")
            st.caption(f"Commit {parts[0]} by {parts[1]}")

        st.divider()

        # ACTIONS
        if st.button("Reset demo", icon=":material/restart_alt:", width="stretch"):
            t = time.perf_counter()
            workspace.reset()
            st.success(f"Workspace reset in {time.perf_counter() - t:.1f}s")
            st.rerun()


def chip(ref: SourceRef | dict) -> str:
    r = SourceRef.model_validate(ref) if isinstance(ref, dict) else ref
    if r.decision:
        return f":violet-badge[D: {r.decision}]"
    if r.commit and not r.doc:
        return f":orange-badge[{r.commit[:7]}]"
    return f":blue-badge[{r.label()}]"


def chips(refs) -> str:
    return " ".join(chip(r) for r in refs if r)


def money(ccy: str, x: float) -> str:
    return f"{ccy} {x:,.2f}"
