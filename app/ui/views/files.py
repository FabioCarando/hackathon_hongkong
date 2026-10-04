"""Files: everything the brain knows, searchable, with where each file is used."""

import pandas as pd
import streamlit as st

from app.core import indexer, reader, search
from app.ui.components import header
from app.ui.trace import setup, sidebar

setup()
sidebar()
files = indexer.build()
new = sum(f.status == "new" for f in files)
header(
    "Everything the brain knows",
    f"{len(files)} files: contracts, invoices, statements, emails and sheets. {new} new.",
)

q = st.text_input(
    "Search all documents", placeholder="lease · bank account changed · 銀行 · SP-4410"
)
if q:
    hits = search.search(q)
    if not hits:
        st.caption("No matches.")
    for h in hits:
        st.markdown(f"**{h['path']}** p.{h['page']} · :gray[{h['score']:.2f}]  \n…{h['snippet']}…")
    st.divider()

c1, c2 = st.columns(2)
kinds = c1.multiselect("Kind", sorted({f.kind for f in files}))
statuses = c2.multiselect("Status", sorted({f.status for f in files}))
shown = [
    f for f in files if (not kinds or f.kind in kinds) and (not statuses or f.status in statuses)
]
icon = {
    "new": "🔵 new",
    "tracked": "⚪ tracked",
    "processed": "🟢 processed",
    "held": "🔴 held",
    "read": "🟡 read",
}
df = pd.DataFrame(
    [
        {
            "file": f.path,
            "kind": f.kind,
            "supplier": f.supplier_id or "",
            "status": icon[f.status],
            "pages": f.pages,
            "read by": f.text_method.replace("_", " "),
            "last commit": (f.last_commit or "")[:7],
            "used in": len(f.used_in),
        }
        for f in shown
    ]
)
event = st.dataframe(
    df, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row"
)
rows = event.selection.rows if event else []
if rows:
    f = shown[rows[0]]
    st.subheader(f.path)
    left, right = st.columns([2, 3])
    with left:
        if f.path.endswith(".pdf"):
            page = st.number_input("Page", 1, f.pages or 1, 1) if (f.pages or 1) > 1 else 1
            st.image(reader.page_png(f.path, page), width="stretch")
        elif reader.can_read(f.path):
            st.text(reader.read(f.path, ocr=False).text[:3000])
    with right:
        st.markdown("**Used in**")
        if not f.used_in:
            st.caption("Not cited by any cell yet.")
        for u in f.used_in:
            st.markdown(f"- `{u}`")
        hit = reader.cached(f.path) if reader.can_read(f.path) else None
        if hit and hit.pages and f.path.endswith(".pdf"):
            with st.expander("Text read from the document"):
                st.text(hit.text[:4000])
