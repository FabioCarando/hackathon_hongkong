"""Entry point: `uv run streamlit run streamlit_app.py`. Add pages to the navigation below."""

import streamlit as st

from app.ui.components import sidebar

st.set_page_config(page_title="Trace", page_icon=":material/account_tree:", layout="wide")

VIEWS = "app/ui/views"
nav = st.navigation(
    {
        "Trace": [
            st.Page(f"{VIEWS}/inbox.py", title="Inbox", icon=":material/inbox:", default=True),
            st.Page(f"{VIEWS}/files.py", title="Files", icon=":material/folder_open:"),
            st.Page(f"{VIEWS}/memory.py", title="Memory", icon=":material/psychology:"),
            st.Page(f"{VIEWS}/history.py", title="History", icon=":material/history:"),
            st.Page(f"{VIEWS}/ask.py", title="Ask the brain", icon=":material/forum:"),
        ],
    }
)
nav.run()
sidebar()
