"""Entry point: `uv run streamlit run streamlit_app.py`. Add pages to the navigation below."""

import streamlit as st

from app.ui.components import sidebar

st.set_page_config(page_title="Hackathon", page_icon=":material/insights:", layout="wide")

VIEWS = "app/ui/views"
nav = st.navigation(
    {
        "Product": [
            st.Page(
                f"{VIEWS}/home.py", title="Overview", icon=":material/dashboard:", default=True
            ),
        ],
        "Dev tools": [
            st.Page(f"{VIEWS}/playground.py", title="LLM playground", icon=":material/chat:"),
            st.Page(f"{VIEWS}/agent.py", title="Agent demo", icon=":material/smart_toy:"),
            st.Page(f"{VIEWS}/calls.py", title="Call log", icon=":material/receipt_long:"),
        ],
    }
)
nav.run()
sidebar()
