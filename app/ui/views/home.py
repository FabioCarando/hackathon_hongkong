"""Product landing page. Replace with the real product once the idea is fixed."""

import streamlit as st

from app.config import settings
from app.llm import get_llm
from app.ui.components import header, llm_errors, stats_row

header("Project name", "One-line value proposition: who it is for and what number it moves.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Provider", "Fake" if settings.llm_provider == "fake" else "Amazon Bedrock", border=True)
c2.metric("Model", settings.llm_model.split(".")[-1], border=True)
c3.metric("Region", settings.aws_region, border=True)
c4.metric("Disk cache", settings.llm_cache.upper(), border=True)

with st.container(border=True):
    st.subheader("Connection check")
    st.caption(
        "One tiny call to the fast model to prove credentials, region and model access work."
    )
    if st.button("Ping Bedrock", type="primary", icon=":material/bolt:"):
        with llm_errors(), st.spinner("Calling Claude..."):
            r = get_llm().complete(
                "Reply with exactly: pong", fast=True, max_tokens=50, label="ping"
            )
            st.success(r.text)
            stats_row(r)
