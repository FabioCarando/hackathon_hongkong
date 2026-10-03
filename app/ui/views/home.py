"""Product landing page. Replace with the real product once the idea is fixed."""

import streamlit as st

from app.config import settings
from app.llm import get_llm
from app.ui.components import PROVIDER_NAMES, header, llm_errors, stats_row

bedrock = settings.llm_provider == "bedrock"

header("Project name", "One-line value proposition: who it is for and what number it moves.")

metrics = {
    "Provider": PROVIDER_NAMES[settings.llm_provider],
    "Model": settings.llm_model.split(".", 1)[-1] if bedrock else settings.llm_model,
    **({"Region": settings.aws_region} if bedrock else {}),
    "Disk cache": settings.llm_cache.upper(),
}
for col, (name, value) in zip(st.columns(len(metrics)), metrics.items()):
    col.metric(name, value, border=True)

with st.container(border=True):
    st.subheader("Connection check")
    st.caption(
        "One tiny call to the fast model to prove the key/credentials and model access work."
    )
    if st.button("Ping model", type="primary", icon=":material/bolt:"):
        with llm_errors(), st.spinner("Calling the model..."):
            r = get_llm().complete(
                "Reply with exactly: pong", fast=True, max_tokens=50, label="ping"
            )
            st.success(r.text)
            stats_row(r)
