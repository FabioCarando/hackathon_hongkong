"""Ask the brain: plain-language questions, answers with sources."""

import streamlit as st

from app.core import ask
from app.ui.components import header, llm_errors, render_step, stats_row
from app.ui.trace import setup, sidebar

setup()
sidebar()
header("Ask the brain", "Every answer cites the documents, commits and decisions behind it.")

SUGGESTED = [
    "Why is 2027 rental income for Flat 12A 98,800?",
    "Why was the Pearl River capital call held?",
    "How much do we still owe Harbourview Capital Partners III?",
    "Which contracts need action in the next 30 days?",
]


def render_answer(text: str) -> None:
    def chip(m):
        kind = m.group(1)
        value = (
            m.group(2)
            .strip()
            .replace("\u2011", "-")
            .removesuffix(" p.null")
            .removesuffix(" p.None")
        )
        ok = ask.validate_ref(kind, value)
        icon = {"doc": "description", "commit": "commit", "decision": "psychology"}[kind]
        color = {"doc": "blue", "commit": "orange", "decision": "violet"}[kind] if ok else "red"
        label = (
            value.rsplit("/", 1)[-1] if kind == "doc" else value[:7] if kind == "commit" else value
        )
        return f" :{color}-badge[:material/{icon}: {label}{'' if ok else ' ⚠ not found'}]"

    st.markdown(ask.REF_RE.sub(chip, text))


cols = st.columns(len(SUGGESTED))
picked = None
for col, q in zip(cols, SUGGESTED):
    if col.button(q, width="stretch"):
        picked = q

question = st.chat_input("Ask about any number, file or decision") or picked
for msg in st.session_state.get("ask_history", []):
    with st.chat_message(msg["role"]):
        render_answer(msg["text"]) if msg["role"] == "assistant" else st.markdown(msg["text"])

if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), llm_errors():
        with st.status("Looking it up…", expanded=False) as status:
            result = ask.ask(question, on_step=render_step)
            status.update(label=f"Checked {len(result.steps)} steps", state="complete")
        render_answer(result.text)
        stats_row(result)
        st.session_state.setdefault("ask_history", []).extend(
            [{"role": "user", "text": question}, {"role": "assistant", "text": result.text}]
        )
