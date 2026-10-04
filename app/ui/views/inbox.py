"""Inbox: what's new. Process documents, review proposed changes, answer Trace's questions."""

from datetime import date

import pandas as pd
import streamlit as st

from app.core import changes, decisions, indexer, intake, reader
from app.core import expectations as ex
from app.core.models import ChangeSet
from app.ui.components import header, llm_errors
from app.ui.trace import STATUS, chips, money, setup, sidebar, user

TODAY = date(2026, 10, 5)  # "today" in the demo data

setup()
sidebar()
header("What's new", "New documents, what Trace read from them, and what it wants to change.")

for d in ex.contract_deadlines(TODAY):
    yearly = f" or commit to USD {d['monthly'] * 12:,.0f} for another year" if d["monthly"] else ""
    st.warning(
        f"**CloudDesk auto-renews {date.fromisoformat(d['renewal_date']):%d %b}.** Cancel by "
        f"**{date.fromisoformat(d['notice_deadline']):%d %b %Y}**{yearly}.  {chips([d['source']])}",
        icon=":material/event:",
    )

pending = intake.pending_docs()
c1, c2 = st.columns([3, 1])
with c1:
    if st.button(
        f"Process {len(pending)} new document{'s' * (len(pending) != 1)}",
        type="primary",
        icon=":material/auto_awesome:",
        disabled=not pending,
    ):
        with llm_errors(), st.status("Reading new documents…", expanded=True) as status:
            css = intake.process_inbox(user(), on_step=st.write)
            indexer.build()
            held = sum(cs.status == "held" for cs in css)
            status.update(
                label=f"Read {len(css)} documents: {len(css) - held} ready, {held} need you",
                state="complete",
                expanded=False,
            )
        st.rerun()

all_cs = changes.all_changesets()
clean = [cs for cs in all_cs if cs.status == "proposed"]
with c2:
    if st.button(
        f"Accept all clean ({len(clean)})",
        icon=":material/done_all:",
        disabled=not clean,
        width="stretch",
    ):
        hashes = [decisions.accept(cs.id, user()) for cs in clean]
        indexer.build()
        st.toast(f"Committed {len(hashes)} changes · last {hashes[-1][:7]}", icon="✅")
        st.rerun()

if not all_cs:
    st.info("Nothing processed yet. New files are waiting in the inbox.", icon=":material/inbox:")


def diff_table(cs: ChangeSet) -> None:
    if cs.new_rows:
        rows = []
        for r in cs.new_rows:
            v = r.values
            rows.append(
                {
                    "file": r.file.rsplit("/", 1)[-1],
                    "date": str(v["date"])[:10],
                    "supplier": v["supplier"],
                    "invoice_no": v["invoice_no"],
                    "amount": f"{v['currency']} {float(v['amount']):,.2f}",
                    "fx": v["fx_rate"],
                    "HKD": f"{float(v['amount']) * float(v['fx_rate']):,.2f}",
                    "account": v["account_code"],
                    "due": str(v["due_date"])[:10],
                    "status": v["status"] if cs.status != "rejected" else "HELD",
                }
            )
        st.caption("New row in the invoice register")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.markdown("Sources: " + chips(cs.new_rows[0].sources))
    if cs.changes:
        df = pd.DataFrame(
            [
                {
                    "file": c.file.rsplit("/", 1)[-1],
                    "sheet": c.sheet,
                    "cell": c.cell,
                    "old": str(c.old),
                    "new": str(c.new),
                }
                for c in cs.changes
            ]
        )
        st.caption("Cells to change")
        st.dataframe(
            df.style.map(
                lambda _: "color: #64748B; text-decoration: line-through", subset=["old"]
            ).map(lambda _: "font-weight: 700; color: #2DD4BF", subset=["new"]),
            hide_index=True,
            width="stretch",
        )
        st.markdown("Source: " + chips(cs.changes[0].sources))


def extracted(cs: ChangeSet) -> None:
    inv = cs.invoice
    ev = inv.evidence
    fields = [
        ("Supplier", f"{inv.supplier_name} ({inv.supplier_id or '?'})", ev.get("supplier")),
        ("Invoice no.", inv.invoice_no, ev.get("invoice_no")),
        ("Date", f"{inv.invoice_date:%d %b %Y}", ev.get("invoice_date")),
        ("Total", money(inv.currency, inv.total), ev.get("total")),
        ("Bank account", inv.bank_account or "—", ev.get("bank_account")),
    ]
    for name, value, ref in fields:
        a, b = st.columns([1, 3])
        a.caption(name)
        b.markdown(f"**{value}** {chips([ref]) if ref else ''}")
    if inv.problems:
        st.warning("Needs review: " + "; ".join(inv.problems), icon=":material/rule:")


def question(cs: ChangeSet) -> None:
    holds = [f for f in cs.findings if f.severity != "approval"]
    st.markdown("**What doesn't fit**" if cs.kind == "invoice" else "**What changed**")
    for f in holds:
        icon = "⛔" if f.severity == "hold" else "📄"
        st.markdown(f"{icon} **{f.title}** · {f.detail}  \n{chips(f.evidence)}  :gray[{f.control}]")
    q = cs.question
    with st.container(border=True):
        st.markdown(f":material/help: **Trace asks:** {q.text}")
        reason = st.text_input(
            "Your reason (required)", key=f"reason-{cs.id}", placeholder="Why? This is saved."
        )
        b1, b2, b3 = st.columns(3)
        answer = None
        if b1.button("Reject", key=f"rej-{cs.id}", icon=":material/block:", width="stretch"):
            answer = "reject"
        if b2.button("Approve once", key=f"once-{cs.id}", width="stretch"):
            answer = "approve_once"
        lock = " 🔒" if q.blocked_options_reason else ""
        if b3.button(
            f"Approve & remember{lock}", key=f"rem-{cs.id}", type="primary", width="stretch"
        ):
            answer = "approve_and_remember"
        if q.blocked_options_reason:
            st.caption(f":material/lock: {q.blocked_options_reason}")
        if answer:
            try:
                d, h = decisions.decide(cs.id, answer, reason, user())
            except decisions.PolicyError as e:
                st.error(str(e), icon=":material/lock:")
                return
            indexer.build()
            st.toast(f"Recorded as {d.id} · committed {h[:7]}", icon="🧠")
            st.rerun()


def card(cs: ChangeSet) -> None:
    color, label = STATUS[cs.status]
    approval = next((f for f in cs.findings if f.control == "APPROVAL-001"), None)
    amount = f" · {money(cs.invoice.currency, cs.invoice.total)}" if cs.invoice else ""
    badge = " :orange-badge[Needs D. Wong approval]" if approval else ""
    doc = cs.trigger.rsplit("/", 1)[-1]
    decided = cs.status in ("accepted", "rejected")
    with st.expander(
        f":{color}-badge[{label}] **{cs.title}**{amount} · `{doc}`{badge}", expanded=not decided
    ):
        left, right = st.columns([2, 3])
        with left:
            pages = reader.page_count(cs.trigger) or 1
            page = 1
            if pages > 1:
                default = cs.lease.evidence.page if cs.lease and cs.lease.evidence.page else 1
                page = st.number_input("Page", 1, pages, default, key=f"pg-{cs.id}")
            st.image(reader.page_png(cs.trigger, page), width="stretch")
        with right:
            if cs.invoice:
                extracted(cs)
            if approval:
                st.markdown(f"🟡 **{approval.title}** · {approval.detail}")
            if cs.status == "held":
                question(cs)
            diff_table(cs)
            if cs.status == "proposed":
                a, b = st.columns(2)
                if a.button(
                    "Accept",
                    key=f"acc-{cs.id}",
                    type="primary",
                    icon=":material/check:",
                    width="stretch",
                ):
                    h = decisions.accept(cs.id, user())
                    indexer.build()
                    st.toast(f"Committed {h[:7]}", icon="✅")
                    st.rerun()
                if b.button("Reject", key=f"rj-{cs.id}", width="stretch"):
                    decisions.reject_clean(cs.id, user())
                    st.rerun()
            if decided:
                who = f"{cs.decided_by}" + (f" · {cs.decision}" if cs.decision else "")
                st.caption(f"{label.title()} by {who} · commit `{(cs.commit or '')[:7]}`")


order = {"held": 0, "proposed": 1, "accepted": 2, "rejected": 2}
for cs in sorted(all_cs, key=lambda c: (order[c.status], c.id)):
    card(cs)
