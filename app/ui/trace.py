"""Shared Trace UI pieces: sidebar (user, brain status, reset), source chips, status badges."""

import time

import streamlit as st

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
    return st.session_state.get("trace_user", "Ken Lau")


def setup() -> None:
    """Call at the top of every Trace page."""
    workspace.ensure()


def sidebar() -> None:
    with st.sidebar:
        st.selectbox("Working as", list(workspace.USERS), key="trace_user", index=1)
        files = indexer.load()
        css = changes.all_changesets()
        c1, c2 = st.columns(2)
        c1.metric("Files", len(files))
        c2.metric("New", sum(f.status == "new" for f in files))
        c1.metric("Open questions", sum(cs.status == "held" for cs in css))
        c2.metric("Decisions", len(decisions.all_decisions()))
        last = workspace.git("log", "-1", "--format=%h · %an", check=False).strip()
        st.caption(f"Last commit: `{last}`")
        if st.button("Reset demo", icon=":material/restart_alt:", width="stretch"):
            t = time.perf_counter()
            workspace.reset()
            st.toast(f"Workspace reset in {time.perf_counter() - t:.1f}s")
            st.rerun()
        st.divider()


def chip(ref: SourceRef | dict) -> str:
    r = SourceRef.model_validate(ref) if isinstance(ref, dict) else ref
    if r.decision:
        return f":violet-badge[:material/psychology: {r.decision}]"
    if r.commit and not r.doc:
        return f":orange-badge[:material/commit: {r.commit[:7]}]"
    return f":blue-badge[:material/description: {r.label()}]"


def chips(refs) -> str:
    return " ".join(chip(r) for r in refs if r)


def money(ccy: str, x: float) -> str:
    return f"{ccy} {x:,.2f}"
