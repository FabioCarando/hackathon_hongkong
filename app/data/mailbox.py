"""Live demo mailbox: pull emails whose subject contains the tag (e.g. "Family Office Inquiry") into the
workspace's mail inbox as .eml files. Read-only (BODY.PEEK: nothing is marked read), tagged
subjects only, and only mail received after the last demo reset."""

import email
import hashlib
import imaplib
from datetime import UTC, datetime
from email import policy
from email.utils import format_datetime, parsedate_to_datetime

from app.config import settings
from app.data import workspace

INBOX = "docs/emails/inbox"
SINCE_FILE = ".trace/mail_since.txt"


def configured() -> bool:
    return bool(settings.trace_imap_user and settings.trace_imap_password)


def mark_reset() -> None:
    """Called on reset: only mail that arrives from now on is demo mail."""
    workspace.path(SINCE_FILE).write_text(datetime.now(UTC).isoformat())


def _since() -> datetime:
    p = workspace.path(SINCE_FILE)
    return (
        datetime.fromisoformat(p.read_text().strip())
        if p.exists()
        else datetime.min.replace(tzinfo=UTC)
    )


def _save(raw: bytes) -> str | None:
    msg = email.message_from_bytes(raw, policy=policy.default)
    key = msg["Message-ID"] or hashlib.sha1(raw).hexdigest()
    name = f"{hashlib.sha1(key.encode()).hexdigest()[:10]}.eml"
    rel = f"{INBOX}/{name}"
    p = workspace.path(rel)
    if p.exists():
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    return rel


def fetch() -> list[str]:
    """New tagged emails -> workspace .eml paths. [] if not configured."""
    if not configured():
        return []
    since = _since()
    new = []
    with imaplib.IMAP4_SSL(settings.trace_imap_host) as m:
        m.login(settings.trace_imap_user, settings.trace_imap_password)
        m.select("INBOX", readonly=True)
        day = since.strftime("%d-%b-%Y") if since.year > 1 else "01-Jan-2026"
        tag = settings.trace_mail_tag.replace('"', "")
        _, data = m.search("UTF-8", "SINCE", day, "SUBJECT", f'"{tag}"'.encode())
        for num in data[0].split()[-20:]:
            _, parts = m.fetch(num, "(BODY.PEEK[])")
            raw = parts[0][1]
            msg = email.message_from_bytes(raw, policy=policy.default)
            if tag.lower() not in (msg["Subject"] or "").lower():
                continue
            try:
                sent = parsedate_to_datetime(msg["Date"])
            except (TypeError, ValueError):
                sent = datetime.now(UTC)
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=UTC)
            if sent < since:
                continue
            if rel := _save(raw):
                new.append(rel)
    return new


def simulate() -> str | None:
    """Offline fallback: re-send the workspace's own bank-change email as a new demo email."""
    from email.message import EmailMessage

    src = next(iter(sorted(workspace.path("docs/emails").glob("*bank_change*.eml"))), None)
    if src is None:
        return None
    old = email.message_from_bytes(src.read_bytes(), policy=policy.default)
    now = datetime.now(UTC)
    msg = EmailMessage()
    msg["From"] = old["From"]
    msg["To"] = old["To"]
    msg["Subject"] = f"{settings.trace_mail_tag} - {old['Subject']}"
    msg["Date"] = format_datetime(now)
    msg["Message-ID"] = f"<{now:%H%M%S%f}@trace-demo>"
    body = old.get_body(preferencelist=("plain",))
    msg.set_content(body.get_content() if body else "")
    return _save(msg.as_bytes())
