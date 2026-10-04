"""Email pieces for the Inbox: live mailbox watcher, email preview + fields."""

import streamlit as st

from app.config import settings
from app.core import indexer, intake, reader
from app.core.models import ChangeSet
from app.data import mailbox
from app.ui.trace import chips, user


def _ingest(paths: list[str]) -> None:
    if not paths:
        return
    css = intake.process_inbox(user())
    indexer.build()
    held = sum(cs.status == "held" for cs in css if cs.kind == "email")
    st.toast(f"📬 {len(paths)} new email{'s' * (len(paths) > 1)} · {held} held by Trace", icon="📬")
    st.rerun(scope="app")


@st.fragment(run_every=10)
def _watch() -> None:
    try:
        new = mailbox.fetch()
    except Exception as e:  # wifi / auth problems must not break the page
        st.caption(f":orange[Mailbox unavailable: {e}]")
        return
    _ingest(new)


def mail_watch() -> None:
    """Live mailbox polling (silent; no status line)."""
    if mailbox.configured():
        _watch()


def email_preview(cs: ChangeSet) -> None:
    em = cs.email
    with st.container(border=True):
        st.markdown(f"**From:** {em.sender_name or ''} `<{em.sender}>`")
        st.markdown(f"**Subject:** {em.subject}")
        if em.received:
            st.caption(f"{em.received:%d %b %Y %H:%M}")
        body = reader.read(cs.trigger).text.split("\n\n", 1)[-1]
        st.text(body[:2000])


def email_fields(cs: ChangeSet) -> None:
    em = cs.email
    fields = [
        (
            "Claims to be",
            f"{em.claimed_supplier or '?'} ({em.supplier_id or 'unknown'})",
            em.evidence.get("supplier"),
        ),
        ("Sent from", em.sender, em.evidence.get("sender")),
        ("Asks for", em.request.replace("_", " "), None),
        ("New account", em.new_bank_account or "—", em.evidence.get("bank_account")),
    ]
    for name, value, ref in fields:
        a, b = st.columns([1, 3])
        a.caption(name)
        b.markdown(f"**{value}** {chips([ref]) if ref else ''}")
    if em.summary:
        st.caption(em.summary)
