"""Memory: what the brain expects, and every decision that taught it."""

import streamlit as st

from app.core import decisions
from app.core import expectations as ex
from app.data import sheets
from app.ui.components import header
from app.ui.trace import chips, setup, sidebar

setup()
sidebar()
header(
    "What the brain expects",
    "Expectations come from contracts and policies; decisions teach it new ones.",
)

exp_tab, dec_tab = st.tabs([":material/psychology: Expectations", ":material/gavel: Decisions"])

KIND = {
    "unit_price": "Contract price",
    "fee_rate": "Fee rate",
    "bank_account": "Bank account",
    "email_domain": "Email domain",
    "recurring_amount": "Recurring amount",
    "approval_limit": "Approval limit",
    "price_tolerance": "Price tolerance",
    "forecast_assumption": "Forecast assumption",
    "contract_term": "Contract term",
    "account_code": "Account code",
}

with exp_tab:
    names = {s["id"]: s["name_en"] for s in sheets.suppliers()} | {"company": "Company policies"}
    items = ex.load()
    for subject in ["company", *sorted({e.subject for e in items} - {"company"})]:
        group = [e for e in items if e.subject == subject]
        with st.expander(
            f"**{names.get(subject, subject)}** · {len(group)}",
            expanded=subject in ("company", "S01"),
        ):
            for e in group:
                learned = f" :violet-badge[learned from {e.learned_from}]" if e.learned_from else ""
                when = f" · from {e.valid_from}" if e.valid_from else ""
                value = e.note or e.value
                st.markdown(
                    f"**{KIND[e.kind]}**{f' `{e.key}`' if e.key and e.kind in ('unit_price', 'account_code') else ''}: "
                    f"{value}{when}{learned}  {chips([e.source])}"
                )

# friendlier names for findings shown on decisions
ABOUT = {"CONTRACT-001": "Harbour Bay Residence"}

with dec_tab:
    ds = decisions.all_decisions()
    if not ds:
        st.info("No decisions yet. They appear when you answer Trace's questions in the Inbox.")
    badge = {
        "reject": ":red-badge[rejected]",
        "approve_once": ":orange-badge[approved once]",
        "approve_and_remember": ":violet-badge[approved & remembered]",
        "enter_blocked": ":red-badge[entered · payment blocked]",
    }
    for d in reversed(ds):
        with st.container(border=True):
            st.markdown(
                f"**{d.id}** {badge[d.answer]} · {d.at:%d %b %H:%M} · **{d.by}** · "
                f"{d.changeset_id} · commit `{(d.commit or '')[:7]}`"
            )
            st.markdown(f":material/format_quote: _{d.reason}_")
            if d.findings:
                st.caption("About: " + ", ".join(ABOUT.get(f, f) for f in d.findings))
            if d.memory_updates:
                st.caption("Memory updated: " + ", ".join(d.memory_updates))
