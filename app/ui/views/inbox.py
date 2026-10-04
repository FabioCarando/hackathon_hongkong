"""Inbox: what's new. Process documents, review proposed changes, answer Trace's questions."""

import time
from datetime import date

import pandas as pd
import streamlit as st

from app.core import changes, decisions, indexer, intake, reader
from app.core import expectations as ex
from app.core.models import ChangeSet
from app.data import sheets
from app.ui.components import llm_errors
from app.ui.mail import email_fields, email_preview, mail_watch
from app.ui.trace import STATUS, chips, money, setup, sidebar, user

TODAY = date(2026, 10, 5)  # "today" in the demo data

setup()
sidebar()

# ============ PROFESSIONAL STYLING ============
st.markdown(
    """
<style>
    /* Professional Hero */
    .hero-title {
        font-size: 2.8rem;
        font-weight: 700;
        margin-bottom: 2.5rem;
        color: inherit;
        letter-spacing: -0.01em;
    }

    /* Professional Buttons */
    .stButton > button {
        font-size: 1rem !important;
        padding: 12px 24px !important;
        height: auto !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12) !important;
        transition: all 0.2s ease !important;
    }

    .stButton > button:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18) !important;
        transform: translateY(-1px) !important;
    }

    /* Professional Cards */
    .card-held {
        border-left: 4px solid #dc2626 !important;
        padding: 1.5rem !important;
        border-radius: 8px !important;
        background: rgba(220, 38, 38, 0.03);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08) !important;
        transition: box-shadow 0.2s ease !important;
    }

    .card-held:hover {
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.12) !important;
    }

    .card-ready {
        border-left: 4px solid #16a34a !important;
        padding: 1.5rem !important;
        border-radius: 8px !important;
        background: rgba(22, 163, 74, 0.03);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08) !important;
        transition: box-shadow 0.2s ease !important;
    }

    .card-ready:hover {
        box-shadow: 0 4px 12px rgba(22, 163, 74, 0.12) !important;
    }

    /* Professional Status */
    .status-held {
        color: #dc2626;
        font-weight: 700;
        font-size: 1rem;
    }

    .status-ready {
        color: #16a34a;
        font-weight: 700;
        font-size: 1rem;
    }

    .status-entered {
        color: #0891b2;
        font-weight: 700;
        font-size: 1rem;
    }

    /* Professional Contract Section */
    .contract-section {
        background: #f9fafb;
        padding: 2rem;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    }

    /* Professional Divider */
    .divider {
        margin: 2.5rem 0;
        border-top: 1px solid #e5e7eb;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ============ MAIN ============
st.markdown('<div class="hero-title">Ready to Trace</div>', unsafe_allow_html=True)

names = {r["id"]: r["name_en"] for r in sheets.suppliers()}
for d in ex.contract_deadlines(TODAY):
    yearly = f" or commit to USD {d['monthly'] * 12:,.0f} for another year" if d["monthly"] else ""
    st.warning(
        f"**{names.get(d['supplier_id'], d['supplier_id'])} auto-renews "
        f"{date.fromisoformat(d['renewal_date']):%d %b}.** Cancel by "
        f"**{date.fromisoformat(d['notice_deadline']):%d %b %Y}**{yearly}.  {chips([d['source']])}",
        icon=":material/event:",
    )

pending = intake.pending_docs()
c1, c2 = st.columns([3, 1])

with c1:
    if st.button(
        f"Process {len(pending)} new document{'s' * (len(pending) != 1)}",
        type="primary",
        key="process_btn",
        disabled=not pending,
    ):
        with llm_errors():
            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.write("Reading documents...")
            css = intake.process_inbox(user(), on_step=st.write)
            progress_bar.progress(60)

            status_text.write("Checking against expectations...")
            indexer.build()
            progress_bar.progress(90)

            status_text.write(f"Done. {len(css)} documents processed.")
            progress_bar.progress(100)

            time.sleep(0.5)

        st.rerun()

mail_watch()

all_cs = changes.all_changesets()
clean = [cs for cs in all_cs if cs.status == "proposed" and cs.kind != "email"]

with c2:
    if st.button(
        f"Accept all ({len(clean)})",
        key="accept_all_btn",
        disabled=not clean,
        width="stretch",
    ):
        hashes = [decisions.accept(cs.id, user()) for cs in clean]
        indexer.build()
        st.toast(f"{len(hashes)} documents entered", icon="✅")
        st.rerun()


def diff_table(cs: ChangeSet) -> None:
    if cs.new_rows:
        rows = []
        for r in cs.new_rows:
            v = r.values
            rows.append(
                {
                    "file": r.file.rsplit("/", 1)[-1],
                    "date": str(v["date"])[:10],
                    "counterparty": v["supplier"],
                    "document no.": v["invoice_no"],
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
        st.markdown("Source: " + chips(cs.new_rows[0].sources))
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
        st.caption("Cell Changes")
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
        ("Counterparty", f"{inv.supplier_name} ({inv.supplier_id or '?'})", ev.get("supplier")),
        ("Document no.", inv.invoice_no, ev.get("invoice_no")),
        ("Date", f"{inv.invoice_date:%d %b %Y}", ev.get("invoice_date")),
        ("Total", money(inv.currency, inv.total), ev.get("total")),
        ("Bank account", inv.bank_account or "—", ev.get("bank_account")),
    ]
    if inv.fee_rate_pct is not None:
        fields.append(("Fee rate", f"{inv.fee_rate_pct:.2f}% a year", ev.get("fee_rate")))
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
        st.markdown(f"**{f.title}** — {f.detail}  \n{chips(f.evidence)}")
    q = cs.question
    with st.container(border=True):
        st.markdown(f"**Trace asks:** {q.text}")
        reason = st.text_input(
            "Your reason (required)", key=f"reason-{cs.id}", placeholder="Why? This is saved."
        )
        b1, b2, b3 = st.columns(3)
        answer = None
        if b1.button("Reject", key=f"rej-{cs.id}", width="stretch"):
            answer = "reject"
        if b2.button("Approve once", key=f"once-{cs.id}", width="stretch"):
            answer = "approve_once"
        if b3.button("Approve & remember", key=f"rem-{cs.id}", type="primary", width="stretch"):
            answer = "approve_and_remember"
        if q.blocked_options_reason:
            st.caption(q.blocked_options_reason)
        if answer:
            try:
                d, h = decisions.decide(cs.id, answer, reason, user())
            except decisions.PolicyError as e:
                st.error(str(e))
                return
            indexer.build()
            st.toast(f"Recorded as {d.id} · committed {h[:7]}", icon="🧠")
            st.rerun()


def card(cs: ChangeSet) -> None:
    color, label = STATUS[cs.status]
    approval = next((f for f in cs.findings if f.control == "APPROVAL-001"), None)
    amount = f" — {money(cs.invoice.currency, cs.invoice.total)}" if cs.invoice else ""
    badge = f" | {approval.title}" if approval else ""
    doc = cs.trigger.rsplit("/", 1)[-1]
    decided = cs.status in ("accepted", "rejected")

    # Status indicator
    if color == "red":
        status_badge = '<span class="status-held">HELD</span>'
    elif color == "green":
        status_badge = '<span class="status-ready">READY</span>'
    else:
        status_badge = f'<span class="status-entered">{label}</span>'

    with st.expander(
        f"{status_badge} **{cs.title}**{amount}",
        expanded=not decided,
    ):
        st.caption(f"Document: `{doc}`{badge}")

        left, right = st.columns([2, 3])
        with left:
            if cs.email:
                email_preview(cs)
                pages = 0
            else:
                pages = reader.page_count(cs.trigger) or 1
            page = 1
            if pages > 1:
                default = cs.lease.evidence.page if cs.lease and cs.lease.evidence.page else 1
                page = st.number_input("Page", 1, pages, default, key=f"pg-{cs.id}")
            if pages:
                st.image(reader.page_png(cs.trigger, page), width="stretch")
        with right:
            if cs.invoice:
                extracted(cs)
            if cs.email:
                email_fields(cs)
            if approval:
                st.info(f"**{approval.title}** — {approval.detail}")
            if cs.status == "held":
                question(cs)
            diff_table(cs)
            if cs.status == "proposed":
                a, b = st.columns(2)
                if a.button(
                    "Accept",
                    key=f"acc-{cs.id}",
                    type="primary",
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
                who = f"{cs.decided_by}" + (f" — {cs.decision}" if cs.decision else "")
                st.caption(f"{label} by {who} · {(cs.commit or '')[:7]}")


# Contract Update
lease_css = [cs for cs in all_cs if cs.kind == "lease"]
if lease_css:
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.subheader("Contract Update")

    for lease_cs in lease_css:
        with st.container(border=True):
            n_cells = sum(
                len(sheets.cells_in(c.cell)) for c in lease_cs.changes if c.sheet == "Forecast"
            )
            ev = lease_cs.lease.evidence if lease_cs.lease else None
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.markdown(f"**{lease_cs.title}**")
            col2.metric("Forecast cells", n_cells)
            col3.metric("Source", f"Lease p.{ev.page}" if ev and ev.page else "Lease")
            st.info(lease_cs.reason)
            if lease_cs.findings:
                st.markdown(chips(lease_cs.findings[0].evidence))

            with st.expander("View changes"):
                diff_table(lease_cs)

            if lease_cs.status == "held":
                reason = st.text_input(
                    "Your reason (required)",
                    key=f"lease_reason_{lease_cs.id}",
                    placeholder="e.g. Renewal signed by Victoria; tenant confirmed",
                )
                col_a, col_b = st.columns(2)
                answer = None
                if col_a.button(
                    "Update forecast & remember",
                    key=f"lease_approve_{lease_cs.id}",
                    type="primary",
                    width="stretch",
                ):
                    answer = "approve_and_remember"
                if col_b.button("Reject", key=f"lease_reject_{lease_cs.id}", width="stretch"):
                    answer = "reject"
                if answer:
                    try:
                        d, h = decisions.decide(lease_cs.id, answer, reason, user())
                    except decisions.PolicyError as e:
                        st.error(str(e))
                    else:
                        indexer.build()
                        st.toast(f"Recorded as {d.id} · committed {h[:7]}", icon="🧠")
                        st.rerun()
            else:
                who = f"{lease_cs.decided_by}" + (
                    f" — {lease_cs.decision}" if lease_cs.decision else ""
                )
                st.caption(f"{STATUS[lease_cs.status][1]} by {who} · {(lease_cs.commit or '')[:7]}")

# Documents
if all_cs:
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    if lease_css:
        st.subheader("Recent Changes")

    order = {"held": 0, "proposed": 1, "accepted": 2, "rejected": 2}
    for cs in sorted(all_cs, key=lambda c: (order[c.status], c.id)):
        if cs.kind != "lease":
            card(cs)
