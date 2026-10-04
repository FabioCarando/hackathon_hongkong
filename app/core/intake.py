"""Orchestration: new document -> read -> extract -> check -> proposed change set (+ question)."""

from collections.abc import Callable
from datetime import date, datetime

from app.core import changes, checks, extractor, reader
from app.core import expectations as ex
from app.core.models import (
    CellChange,
    ChangeSet,
    Expectation,
    Finding,
    InvoiceData,
    LeaseTerms,
    NewRow,
    Question,
    SourceRef,
)
from app.data import sheets, workspace

REGISTER = "sheets/invoice_register.xlsx"
FORECAST = "sheets/forecast_2027_2028.xlsx"
MASTER = "sheets/supplier_master.xlsx"
GUARDED = {"BANK-001", "DOMAIN-001"}  # COMPANY.md: bank changes need a call-back


def pending_docs() -> list[str]:
    """New (untracked) inbox invoices and contracts that have no change set yet."""
    done = {cs.trigger for cs in changes.all_changesets()}
    new = workspace.untracked()
    docs = [
        p
        for p in sorted(new)
        if p.endswith(".pdf")
        and (p.startswith("docs/invoices/inbox/") or p.startswith("docs/contracts/"))
        and p not in done
    ]
    return docs


def process_inbox(user: str, on_step: Callable[[str], None] = lambda s: None) -> list[ChangeSet]:
    out = []
    for rel in pending_docs():
        scanned = reader.needs_ocr(rel)
        on_step(f"Reading {rel.rsplit('/', 1)[-1]}" + (" (scanned → OCR)" if scanned else ""))
        try:
            reader.read(rel)
            if rel.startswith("docs/contracts/"):
                cs = _lease_changeset(rel, user, on_step)
            else:
                cs = _invoice_changeset(rel, user, on_step)
        except Exception as e:  # keep going: one bad document must not stop the inbox
            on_step(f"⚠️ Could not process {rel}: {e}")
            continue
        if cs:
            changes.save(cs)
            out.append(cs)
    return out


# -- invoices ---------------------------------------------------------------------------------


def _invoice_changeset(rel: str, user: str, on_step) -> ChangeSet:
    inv = extractor.extract_invoice(rel)
    who = next(
        (s["name_en"] for s in sheets.suppliers() if s["id"] == inv.supplier_id), inv.supplier_name
    )
    on_step(f"Checking {who} {inv.invoice_no} against what the brain expects")
    findings = checks.run(inv)
    master = next((s for s in sheets.suppliers() if s["id"] == inv.supplier_id), None)
    fx = sheets.fx_rate(inv.currency, inv.invoice_date)
    acct = ex.get(inv.supplier_id, "account_code") if inv.supplier_id else None
    sources = [
        inv.evidence[k]
        for k in ("invoice_no", "invoice_date", "total", "supplier")
        if k in inv.evidence
    ]
    sources.append(
        SourceRef(doc="sheets/fx_rates.xlsx", quote=f"{inv.invoice_date:%Y-%m} {inv.currency} {fx}")
    )
    held = any(f.severity == "hold" for f in findings)
    approval = any(f.control == "APPROVAL-001" for f in findings)
    name = master["name_en"] if master else inv.supplier_name
    reason = (
        f"Entered {name} invoice {inv.invoice_no} ({inv.currency} {inv.total:,.2f}) from {rel}."
    )
    if approval:
        reason += " Above HK$50,000: needs D. Wong approval before payment."
    row = NewRow(
        file=REGISTER,
        sheet="Register",
        values={
            "date": inv.invoice_date,
            "supplier_id": inv.supplier_id,
            "supplier": name,
            "invoice_no": inv.invoice_no,
            "currency": inv.currency,
            "amount": inv.total,
            "fx_rate": fx,
            "account_code": str(acct.value) if acct else None,
            "due_date": inv.due_date,
            "status": "HELD" if held else "Entered",
            "source_file": rel,
        },
        sources=sources,
        reason=reason,
    )
    cs = ChangeSet(
        id=changes.new_id(),
        title=f"Enter {name} invoice {inv.invoice_no}",
        reason=reason,
        trigger=rel,
        kind="invoice",
        new_rows=[row],
        findings=findings,
        status="held" if held else "proposed",
        created_by=user,
        created_at=datetime.now(),
        invoice=inv,
        memory_updates=_invoice_memory(inv, findings),
    )
    if held:
        cs.question = _question(cs)
    return cs


def _invoice_memory(inv: InvoiceData, findings: list[Finding]) -> list[Expectation]:
    out = []
    src = SourceRef(doc=inv.evidence.get("total", SourceRef(doc="")).doc, page=1)
    for f in findings:
        if f.control == "PRICE-001" and f.expectation_id:
            old = next(e for e in ex.load() if e.id == f.expectation_id)
            out.append(
                old.model_copy(
                    update=dict(
                        id=f"{old.id}-from-{inv.invoice_date}",
                        value=f.actual,
                        valid_from=inv.invoice_date,
                        note=f"Price changed to {inv.currency} {float(f.actual):,.2f} from {inv.invoice_no}",
                        source=src,
                    )
                )
            )
        elif f.control == "BANK-001" and f.expectation_id:
            out.append(
                Expectation(
                    id=f"E-{inv.supplier_id}-bank-from-{inv.invoice_date}",
                    subject=inv.supplier_id,
                    kind="bank_account",
                    value=str(f.actual),
                    valid_from=inv.invoice_date,
                    note="Bank account change verified by call-back",
                    source=src,
                )
            )
        elif f.control == "DOMAIN-001":
            for d in str(f.actual).split(", "):
                out.append(
                    Expectation(
                        id=f"E-{inv.supplier_id}-domain-{d}",
                        subject=inv.supplier_id,
                        kind="email_domain",
                        value=d,
                        source=src,
                    )
                )
    return out


# -- new contract (lease) -----------------------------------------------------------------------


def _lease_changeset(rel: str, user: str, on_step) -> ChangeSet | None:
    on_step("Reading the rent terms of the new lease")
    terms = extractor.extract_lease(rel)
    assumption = ex.get("company", "forecast_assumption", "rent_monthly")
    current = float(assumption.value) if assumption else None
    if current is not None and abs(current - terms.rent_monthly) < 0.01:
        return None
    on_step("New rent differs from the forecast assumption → proposing a forecast update")
    y1 = round(terms.rent_monthly, 2)
    y2 = round(terms.rent_monthly * (1 + terms.escalation_pct / 100), 2)
    old = sheets.read_range(FORECAST, "Forecast", "C9:Z9")
    src = [terms.evidence]
    if assumption:
        src_old = [assumption.source]
    else:
        src_old = []
    signed = f"{terms.signed:%d %b %Y}" if terms.signed else "recently"
    reason = (
        f"New lease {terms.reference or ''} signed {signed}: rent HK${y1:,.0f}/month from "
        f"{terms.rent_from:%d %b %Y}, +{terms.escalation_pct:g}% each January "
        f"(HK${y2:,.0f} in 2028). Replaces the HK${current:,.0f} flat assumption."
    ).replace("  ", " ")
    master_row = next(
        s["_row"] for s in sheets.suppliers() if s["id"] == (terms.supplier_id or "S04")
    )
    cs = ChangeSet(
        id=changes.new_id(),
        title=f"Update rent forecast from new lease ({rel.rsplit('/', 1)[-1]})",
        reason=reason,
        trigger=rel,
        kind="lease",
        changes=[
            CellChange(
                file=FORECAST,
                sheet="Forecast",
                cell="C9:N9",
                old=old["C9"],
                new=y1,
                sources=src,
                reason=reason,
            ),
            CellChange(
                file=FORECAST,
                sheet="Forecast",
                cell="O9:Z9",
                old=old["O9"],
                new=y2,
                sources=src,
                reason=reason,
            ),
            CellChange(
                file=FORECAST,
                sheet="Assumptions",
                cell="B4",
                old=sheets.read_range(FORECAST, "Assumptions", "B4")["B4"],
                new=f"HK${y1:,.0f}/month 2027, +{terms.escalation_pct:g}%/yr (HK${y2:,.0f} 2028)",
                sources=src,
                reason=reason,
            ),
            CellChange(
                file=FORECAST,
                sheet="Assumptions",
                cell="C4",
                old=sheets.read_range(FORECAST, "Assumptions", "C4")["C4"],
                new=f"Lease {terms.reference or rel} p.{terms.evidence.page} cl.4, signed {signed}",
                sources=src,
                reason=reason,
            ),
            CellChange(
                file=MASTER,
                sheet="Suppliers",
                cell=f"I{master_row}",
                old=sheets.read_range(MASTER, "Suppliers", f"I{master_row}")[f"I{master_row}"],
                new=rel,
                sources=src,
                reason="New lease replaces the 2024-26 lease as the S04 contract.",
            ),
        ],
        findings=[
            Finding(
                control="CONTRACT-001",
                severity="info",
                title="New lease changes the rent forecast",
                detail=(
                    f"Lease: HK${y1:,.0f}/month from {terms.rent_from:%d %b %Y}, +{terms.escalation_pct:g}%/yr. "
                    f"Forecast assumes HK${current:,.0f} flat (D. Wong, Aug 2026). 24 forecast cells would change."
                ),
                expected=current,
                actual=y1,
                evidence=src + src_old,
                expectation_id=assumption.id if assumption else None,
            )
        ],
        status="held",
        created_by=user,
        created_at=datetime.now(),
        lease=terms,
        memory_updates=_lease_memory(terms, y1, y2),
    )
    cs.question = _question(cs)
    return cs


def _lease_memory(t: LeaseTerms, y1: float, y2: float) -> list[Expectation]:
    return [
        Expectation(
            id="E-company-rent-2027",
            subject="company",
            kind="forecast_assumption",
            key="rent_monthly",
            value=y1,
            valid_from=t.rent_from,
            note=f"Rent HK${y1:,.0f} in 2027, HK${y2:,.0f} in 2028 (+{t.escalation_pct:g}%/yr) per new lease",
            source=t.evidence,
        ),
        Expectation(
            id="E-S04-recurring-2027",
            subject=t.supplier_id or "S04",
            kind="recurring_amount",
            value=y1,
            tolerance=0.01,
            valid_from=t.rent_from,
            valid_to=date(t.rent_from.year, 12, 31),
            note=f"Monthly rent HK${y1:,.0f} from {t.rent_from:%b %Y}",
            source=t.evidence,
        ),
    ]


# -- questions --------------------------------------------------------------------------------


def _question(cs: ChangeSet) -> Question:
    controls = {f.control for f in cs.findings}
    guarded = controls & GUARDED
    if cs.kind == "lease":
        f = cs.findings[0]
        text = f"{cs.reason} Your forecast still assumes HK${float(f.expected):,.0f} flat. Update the forecast?"
    else:
        text = _llm_question(cs) or _template_question(cs)
    return Question(
        text=text,
        options=["reject", "approve_once", "approve_and_remember"],
        blocked_options_reason=(
            "Bank or sender changes can't be remembered without a call-back to a known number "
            "(COMPANY.md: email alone is never enough). Mention the call-back in your reason."
            if guarded
            else None
        ),
    )


def _template_question(cs: ChangeSet) -> str:
    issues = "; ".join(
        f"{f.title.lower()} ({f.detail})" for f in cs.findings if f.severity == "hold"
    )
    return f"{cs.title}: this doesn't match what I expect: {issues}. Was this expected? Why?"


def _llm_question(cs: ChangeSet) -> str | None:
    from app.llm import get_llm

    facts = "\n".join(f"- {f.title}: {f.detail}" for f in cs.findings if f.severity == "hold")
    prompt = (
        f"An incoming document was stopped before entering the books.\nDocument: {cs.title}\n"
        f"Problems found by the checks:\n{facts}\n\nWrite ONE short paragraph (max 3 sentences) to the "
        "finance clerk: say plainly what doesn't fit, with the numbers, and ask whether this was "
        "expected and why. No greeting, no markdown, no advice beyond the question."
    )
    try:
        text = get_llm().complete(prompt, fast=True, max_tokens=400, label="question").text.strip()
    except Exception:
        return None
    return text or None
