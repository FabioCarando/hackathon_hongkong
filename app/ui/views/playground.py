"""Try prompts against the live model: streaming text and structured extraction."""

from typing import Literal

import streamlit as st
from pydantic import BaseModel, Field

from app.llm import get_llm
from app.ui.components import header, llm_errors, stats_row

header("LLM playground", "Streamed completions and pydantic-validated structured output.")

llm = get_llm()
fast = st.toggle("Use fast model", value=False)
chat_tab, extract_tab = st.tabs([":material/chat: Stream", ":material/data_object: Extract"])

with chat_tab:
    system = st.text_area("System prompt", "You are a concise financial-services analyst.")
    prompt = st.text_area("Prompt", "Explain in 3 bullets what an STR is in Hong Kong.")
    if st.button("Run", type="primary", key="run_stream"):
        with llm_errors():
            stream = llm.stream(prompt, system=system, fast=fast, label="playground")
            with st.container(border=True):
                st.write_stream(stream)
            if stream.result:
                stats_row(stream.result)


class RiskAssessment(BaseModel):
    """Example schema: replace with whatever your product needs to extract."""

    risk_level: Literal["low", "medium", "high"]
    red_flags: list[str] = Field(description="Specific suspicious facts found in the text")
    recommended_action: str
    confidence: float = Field(ge=0, le=1)


with extract_tab:
    text = st.text_area(
        "Input",
        "Client opened account 3 days ago, deposited HKD 480,000 from a third-party account, "
        "made no trades, and requested a withdrawal to a newly added bank account in another name.",
        height=120,
    )
    if st.button("Extract", type="primary", key="run_extract"):
        with llm_errors(), st.spinner("Extracting..."):
            obj, result = llm.extract(
                f"Assess this account activity:\n\n{text}",
                RiskAssessment,
                fast=fast,
                label="extract",
            )
            colour = {"low": "green", "medium": "orange", "high": "red"}[obj.risk_level]
            st.markdown(f"### Risk: :{colour}-badge[{obj.risk_level.upper()}]")
            st.json(obj.model_dump())
            stats_row(result)
