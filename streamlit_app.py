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
        "Dev tools": [
            st.Page(f"{VIEWS}/home.py", title="Connection check", icon=":material/dashboard:"),
            st.Page(f"{VIEWS}/playground.py", title="LLM playground", icon=":material/chat:"),
            st.Page(f"{VIEWS}/agent.py", title="Agent demo", icon=":material/smart_toy:"),
            st.Page(f"{VIEWS}/calls.py", title="Call log", icon=":material/receipt_long:"),
        ],
    }
)
nav.run()
sidebar()
