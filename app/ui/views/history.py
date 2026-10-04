"""History: every change and why. Commit timeline + cell blame."""

import streamlit as st

from app.core import versioning
from app.data import sheets, workspace
from app.ui.components import header
from app.ui.trace import chips, setup, sidebar

setup()
sidebar()
header("Every change and why", "The workspace's version history, and the story of any cell.")

blame, timeline = st.tabs([":material/manage_search: Cell history", ":material/history: Timeline"])

with blame:
    files = {
        "sheets/forecast_2027_2028.xlsx": ["Forecast", "Assumptions"],
        "sheets/invoice_register.xlsx": ["Register"],
        "sheets/supplier_master.xlsx": ["Suppliers"],
    }
    c1, c2, c3 = st.columns([3, 2, 1])
    file = c1.selectbox("File", list(files), format_func=lambda f: f.rsplit("/", 1)[-1])
    sheet = c2.selectbox("Sheet", files[file])
    cell = c3.text_input("Cell", "C9" if sheet == "Forecast" else "F19").strip().upper()
    try:
        now = sheets.read_range(file, sheet, cell)[cell]
    except Exception:
        now = None
    st.metric(f"{sheet}!{cell} now", f"{now:,.0f}" if isinstance(now, (int, float)) else str(now))
    hist = versioning.history(file, sheet, cell)
    if not hist:
        st.info("No recorded changes for this cell.")
    for e in hist:
        with st.container(border=True):
            v = e.get("value")
            val = f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
            st.markdown(
                f"**{val}** · {e.get('commit_date', '')} · **{e.get('commit_author', '')}** · "
                f"`{(e.get('commit') or '')[:7]}` {e.get('commit_subject', '')}"
            )
            st.markdown(f":material/format_quote: {e['reason']}")
            refs = list(e.get("sources", []))
            if e.get("decision"):
                refs.append({"decision": e["decision"]})
            st.markdown(chips(refs))
            for s in e.get("sources", []):
                if s.get("quote"):
                    st.caption(f"“{s['quote']}” — {s['doc'].rsplit('/', 1)[-1]}")

with timeline:
    for c in workspace.log():
        trace = c["author"] in workspace.USERS and c["date"] >= "2026-10-04"
        with st.expander(
            f"`{c['hash'][:7]}` · {c['date']} · **{c['author']}** · {c['subject']}"
            + (" :green-badge[Trace]" if trace else "")
        ):
            if c["body"]:
                st.text(c["body"])
            st.caption("Files: " + ", ".join(f"`{f}`" for f in c["files"]))
            cells = versioning.for_commit(c["hash"])
            for e in cells:
                st.markdown(
                    f"- `{e['file'].rsplit('/', 1)[-1]}!{e['sheet']}!{e['cell']}` → {e.get('value')}  {chips(e.get('sources', []))}"
                )
