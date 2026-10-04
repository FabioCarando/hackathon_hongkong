"""Text -> structured data. The LLM reads the fields; code checks arithmetic, matches the supplier,
and locates the evidence (page + quote) for each key value in the page text."""

import difflib
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.core import reader
from app.core.models import InvoiceData, InvoiceLine, LeaseTerms, ReadResult, SourceRef
from app.data import sheets, workspace
from app.llm import get_llm

OWN_DOMAIN = "harbourlane.com.hk"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class _InvoiceLLM(BaseModel):
    supplier_name: str
    invoice_no: str
    invoice_date: str  # YYYY-MM-DD
    due_date: str | None = None  # YYYY-MM-DD, only if printed
    currency: Literal["HKD", "RMB", "USD"]
    lines: list[InvoiceLine]
    subtotal: float
    tax: float
    total: float
    bank_account: str | None = None  # the supplier's account number printed for payment


class _LeaseLLM(BaseModel):
    reference: str | None = None
    signed: str | None = None  # YYYY-MM-DD
    rent_monthly: float  # first-year monthly rent
    rent_from: str  # YYYY-MM-DD
    escalation_pct: float  # yearly increase in percent, e.g. 3.0


INVOICE_SYSTEM = (
    "You extract fields from supplier invoices for a Hong Kong finance team. Copy values exactly "
    "as printed. Dates as YYYY-MM-DD. Currency: CNY / RMB / 人民币 / ¥ -> RMB; US$ -> USD; HK$ -> "
    "HKD. Amounts as plain numbers without separators. bank_account is the supplier's receiving "
    "account number, exactly as printed. Include every line item with its item code if printed."
)


def _pages_prompt(rr: ReadResult) -> str:
    return "\n\n".join(f"=== Page {p.page} ===\n{p.text}" for p in rr.pages)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_quote(rr: ReadResult, *needles: str) -> SourceRef | None:
    """First page line containing any needle -> SourceRef(doc, page, quote=line)."""
    for needle in needles:
        if not needle:
            continue
        n = _norm(needle).lower()
        for p in rr.pages:
            for line in p.text.splitlines():
                if n in _norm(line).lower():
                    return SourceRef(doc=rr.path, page=p.page, quote=_norm(line))
    return None


def _money_variants(x: float) -> list[str]:
    return [f"{x:,.2f}", f"{x:,.0f}", f"{x:.2f}", f"{x:.0f}"]


def match_supplier(name: str, text: str) -> tuple[str | None, dict | None]:
    best, score = None, 0.0
    for s in sheets.suppliers():
        for n in (s["name_en"], s["name_zh"]):
            if not n:
                continue
            r = difflib.SequenceMatcher(None, name.lower(), n.lower()).ratio()
            if n.lower() in text.lower():
                r = max(r, 0.9)
            if r > score:
                best, score = s, r
    return (best["id"], best) if best and score >= 0.6 else (None, None)


def linked_emails(invoice_no: str, filename: str) -> list[tuple[str, SourceRef]]:
    """(sender, evidence) for emails in docs/emails that mention this invoice or attach the file."""
    out = []
    for p in sorted(workspace.path("docs/emails").glob("*.eml")):
        rel = p.relative_to(workspace.root()).as_posix()
        rr = reader.read(rel)
        if invoice_no in rr.text or filename in rr.text:
            m = re.search(r"^From: .*?<?([\w.+-]+@[\w.-]+)>?$", rr.text, re.M)
            if m:
                out.append((m.group(1), SourceRef(doc=rel, page=1, quote=_norm(m.group(0)))))
    return out


def extract_invoice(rel: str) -> InvoiceData:
    rr = reader.read(rel)
    raw, _ = get_llm().extract(
        _pages_prompt(rr), _InvoiceLLM, system=INVOICE_SYSTEM, label="extract_invoice"
    )
    problems = []
    inv_date = date.fromisoformat(raw.invoice_date)
    sid, master = match_supplier(raw.supplier_name, rr.text)
    due = date.fromisoformat(raw.due_date) if raw.due_date else None
    if due is None and master:
        days = int(re.match(r"\d+", master["payment_terms"]).group())
        due = inv_date + timedelta(days=days)

    for ln in raw.lines:
        if abs(ln.qty * ln.unit_price - ln.amount) > 0.01:
            problems.append(f"Line {ln.item_code or ln.description}: qty x price != amount")
    if raw.lines and abs(sum(ln.amount for ln in raw.lines) - raw.subtotal) > 0.01:
        problems.append("Sum of lines != subtotal")
    if abs(raw.subtotal + raw.tax - raw.total) > 0.01:
        problems.append("Subtotal + tax != total")

    ev: dict[str, SourceRef] = {}
    if q := find_quote(rr, raw.invoice_no):
        ev["invoice_no"] = q
    if q := find_quote(rr, *_money_variants(raw.total)):
        ev["total"] = q
    if master and (
        q := find_quote(rr, master["name_zh"] or "", master["name_en"], raw.supplier_name)
    ):
        ev["supplier"] = q
    if raw.bank_account:
        digits = re.sub(r"\D", "", raw.bank_account)
        if q := find_quote(rr, raw.bank_account, digits[-4:]):
            ev["bank_account"] = q
    if q := find_quote(
        rr, raw.invoice_date, inv_date.strftime("%d %b %Y"), inv_date.strftime("%B %d, %Y")
    ):
        ev["invoice_date"] = q
    for ln in raw.lines:
        if ln.item_code and (q := find_quote(rr, ln.item_code)):
            ev[f"line:{ln.item_code}"] = q
    for key in ("invoice_no", "total"):
        if key not in ev:
            problems.append(f"Could not find {key} in the document text")

    senders = [e for e in EMAIL_RE.findall(rr.text) if not e.lower().endswith(OWN_DOMAIN)]
    for e in senders:
        if q := find_quote(rr, e):
            ev.setdefault(f"email:{e}", q)
    for e, ref in linked_emails(raw.invoice_no, Path(rel).name):
        senders.append(e)
        ev.setdefault(f"email:{e}", ref)

    return InvoiceData(
        supplier_name=raw.supplier_name,
        supplier_id=sid,
        invoice_no=raw.invoice_no.strip(),
        invoice_date=inv_date,
        due_date=due,
        currency=raw.currency,
        lines=raw.lines,
        subtotal=raw.subtotal,
        tax=raw.tax,
        total=raw.total,
        bank_account=raw.bank_account,
        sender_emails=sorted(set(senders)),
        evidence=ev,
        problems=problems,
    )


def extract_lease(rel: str) -> LeaseTerms:
    rr = reader.read(rel)
    raw, _ = get_llm().extract(
        _pages_prompt(rr),
        _LeaseLLM,
        system="Extract the rent terms of this tenancy agreement. Dates as YYYY-MM-DD.",
        label="extract_contract",
    )
    sid, _ = match_supplier("Kowloon Bay Properties Ltd", rr.text)
    q = find_quote(rr, *_money_variants(raw.rent_monthly)) or SourceRef(doc=rel)
    q.clause = "4"
    return LeaseTerms(
        supplier_id=sid,
        reference=raw.reference,
        signed=date.fromisoformat(raw.signed) if raw.signed else None,
        rent_monthly=raw.rent_monthly,
        rent_from=date.fromisoformat(raw.rent_from),
        escalation_pct=raw.escalation_pct,
        evidence=q,
    )
