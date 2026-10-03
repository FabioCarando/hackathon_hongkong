"""Tool-using agent with every step shown live. Swap the demo tools for real ones."""

import streamlit as st

from app.llm import AgentStep, get_llm, tool
from app.ui.components import header, llm_errors, render_step, stats_row

header("Agent demo", "The model calls Python tools; each call and result is shown as it happens.")

ACCOUNTS = {
    "C-1001": {"name": "Chan Tai Man", "balance_hkd": 12_500, "opened": "2024-03-02"},
    "C-1002": {"name": "Wong Mei Ling", "balance_hkd": 480_000, "opened": "2026-09-29"},
}
FX = {"USDHKD": 7.78, "EURHKD": 8.45, "CNHHKD": 1.09}


@tool(example={"account_id": "C-1002"})
def get_account(account_id: str) -> dict:
    """Fetch a client account by ID (e.g. C-1001). Returns name, balance in HKD and open date."""
    if account_id not in ACCOUNTS:
        raise KeyError(f"unknown account {account_id}")
    return ACCOUNTS[account_id]


@tool(example={"pair": "USDHKD"})
def get_fx_rate(pair: str) -> float:
    """Spot FX rate for a currency pair written like USDHKD."""
    return FX[pair.upper()]


prompt = st.text_input(
    "Task", "What is account C-1002's balance in USD, and is anything unusual about it?"
)
if st.button("Run agent", type="primary", icon=":material/play_arrow:"):
    with llm_errors():
        with st.status("Agent working...", expanded=True) as status:

            def on_step(step: AgentStep) -> None:
                if step.kind != "text":
                    render_step(step)

            result = get_llm().run_agent(
                prompt,
                tools=[get_account, get_fx_rate],
                system="You are a careful operations analyst. Use tools; never guess numbers.",
                on_step=on_step,
            )
            status.update(label=f"Done in {len(result.calls)} model calls", state="complete")
        with st.container(border=True):
            st.markdown(result.text)
        stats_row(result)
