"""Orchestration: new document -> read -> extract -> check -> proposed change set (+ question)."""

import re
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
from app.data import company, sheets, workspace

REGISTER = "sheets/invoice_register.xlsx"
MASTER = "sheets/supplier_master.xlsx"
DOC_NAMES = {"invoice": "invoice", "capital_call": "capital call", "fee_notice": "fee notice"}
GUARDED = {"BANK-001", "DOMAIN-001"}  # COMPANY.md: bank changes need a call-back


def pending_docs() -> list[str]:
    """New (untracked) inbox invoices and contracts that have no change set yet."""
    done = {cs.trigger for cs in changes.all_changesets()}
    new = workspace.untracked()
    docs = [
        p
        for p in sorted(new)
        if p not in done
        and (
            (p.endswith(".pdf") and p.startswith(("docs/invoices/inbox/", "docs/contracts/")))
            or (p.endswith(".eml") and p.startswith("docs/emails/inbox/"))
        )
    ]
    return docs


def process_inbox(user: str, on_step: Callable[[str], None] = lambda s: None) -> list[ChangeSet]:
    out = []
    for rel in pending_docs():
        scanned = reader.needs_ocr(rel)
        on_step(f"Reading {rel.rsplit('/', 1)[-1]}" + (" (scanned → OCR)" if scanned else ""))
        try:
            reader.read(rel)
            if rel.endswith(".eml"):
                cs = _email_changeset(rel, user, on_step)
            elif rel.startswith("docs/contracts/"):
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


def recheck_open(on_step: Callable[[str], None] = lambda s: None) -> list[ChangeSet]:
    """Re-run the checks on open invoices after the memory changed (e.g. a fraud was rejected).
    Returns the change sets whose findings changed."""
    changed = []
    for cs in changes.all_changesets():
        if cs.kind != "invoice" or cs.status not in ("proposed", "held") or not cs.invoice:
            continue
        findings = checks.run(cs.invoice)
        if {f.control for f in findings} == {f.control for f in cs.findings}:
            continue
        cs.findings = findings
        held = any(f.severity == "hold" for f in findings)
        cs.status = "held" if held else "proposed"
        cs.memory_updates = _invoice_memory(cs.invoice, findings)
        cs.question = _question(cs) if held else None
        changes.save(cs)
        on_step(f"Re-checked {cs.title}: {', '.join(sorted(f.control for f in findings))}")
        changed.append(cs)
    return changed


# -- emails -----------------------------------------------------------------------------------


def _email_changeset(rel: str, user: str, on_step) -> ChangeSet:
    em = extractor.extract_email(rel)
    on_step(f"Checking email from {em.sender} ({em.claimed_supplier or 'unknown sender'})")
    findings = checks.run_email(em)
    held = any(f.severity == "hold" for f in findings)
    src = SourceRef(doc=rel, page=1, quote=em.evidence.get("bank_account", SourceRef()).quote)
    who = (em.claimed_supplier or em.sender).rstrip(".")
    cs_changes: list[CellChange] = []
    memory: list[Expectation] = []
    master = next((s for s in sheets.suppliers() if s["id"] == em.supplier_id), None)
    if em.request == "bank_change" and em.new_bank_account and master:
        r = master["_row"]
        reason = (
            f"Bank details changed for {master['name_en']} as requested by email from {em.sender}."
        )
        cs_changes = [
            CellChange(
                file=MASTER,
                sheet="Suppliers",
                cell=f"E{r}",
                old=master["bank_name"],
                new=em.bank_name or master["bank_name"],
                sources=[src],
                reason=reason,
            ),
            CellChange(
                file=MASTER,
                sheet="Suppliers",
                cell=f"F{r}",
                old=master["bank_account"],
                new=em.new_bank_account,
                sources=[src],
                reason=reason,
            ),
        ]
        memory.append(
            Expectation(
                id=f"E-{em.supplier_id}-bank-from-email",
                subject=em.supplier_id,
                kind="bank_account",
                value=em.new_bank_account,
                valid_from=(em.received or datetime.now()).date(),
                note=f"Changed by email from {em.sender}, verified by call-back",
                source=src,
            )
        )
    reject_memory = []
    if held:
        reject_memory.append(
            Expectation(
                id=f"E-blocked-sender-{em.sender}",
                subject=em.supplier_id or "company",
                kind="blocked_sender",
                value=em.sender,
                note=f"Email '{em.subject}' claimed to be {who}.",
                source=SourceRef(
                    doc=rel, page=1, quote=em.evidence.get("sender", SourceRef()).quote
                ),
            )
        )
        if em.new_bank_account:
            reject_memory.append(
                Expectation(
                    id=f"E-blocked-bank-{''.join(c for c in em.new_bank_account if c.isdigit())}",
                    subject=em.supplier_id or "company",
                    kind="blocked_bank",
                    value=em.new_bank_account,
                    note=f"Requested by {em.sender}, claiming to be {who}.",
                    source=src,
                )
            )
    cs = ChangeSet(
        id=changes.new_id(),
        title=f"Email from {who}: {em.request.replace('_', ' ')}",
        reason=em.summary or em.subject,
        trigger=rel,
        kind="email",
        changes=cs_changes,
        findings=findings,
        status="held" if held else "proposed",
        created_by=user,
        created_at=datetime.now(),
        email=em,
        memory_updates=memory,
        reject_memory=reject_memory,
    )
    if held:
        cs.question = _question(cs)
    return cs


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
    acct = (ex.get("company", "account_code", inv.kind) if inv.kind != "invoice" else None) or (
        ex.get(inv.supplier_id, "account_code") if inv.supplier_id else None
    )
    sources = [
        inv.evidence[k]
        for k in ("invoice_no", "invoice_date", "total", "supplier")
        if k in inv.evidence
    ]
    sources.append(
        SourceRef(doc="sheets/fx_rates.xlsx", quote=f"{inv.invoice_date:%Y-%m} {inv.currency} {fx}")
    )
    held = any(f.severity == "hold" for f in findings)
    approval = next((f for f in findings if f.control == "APPROVAL-001"), None)
    name = master["name_en"] if master else inv.supplier_name
    doc_name = DOC_NAMES[inv.kind]
    reason = (
        f"Entered {name} {doc_name} {inv.invoice_no} ({inv.currency} {inv.total:,.2f}) from {rel}."
    )
    if approval:
        reason += f" {approval.detail} {approval.title} before payment."
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
        title=f"Enter {name} {doc_name} {inv.invoice_no}",
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


def _forecast_cells() -> tuple[str, str, dict[int, str]]:
    """(workbook, sheet, {year: 'C5:N5'}) for the rent forecast named range, split by year using
    the month headers ('Jan-27') above it."""
    name, file = company.forecast_range()
    sheet, ref = sheets.named_range(file, name)
    cells = sheets.cells_in(ref)
    first_row = int("".join(ch for ch in cells[0] if ch.isdigit()))
    col = "".join(ch for ch in cells[0] if ch.isalpha())
    head_row = next(
        r
        for r in range(first_row - 1, 0, -1)
        if re.fullmatch(
            r"[A-Z][a-z]{2}-\d{2}", str(sheets.read_range(file, sheet, f"{col}{r}")[f"{col}{r}"])
        )
    )
    heads = sheets.read_range(
        file,
        sheet,
        f"{cells[0][: len(col)]}{head_row}:{cells[-1][: -len(str(first_row))]}{head_row}",
    )
    years: dict[int, list[str]] = {}
    for c, h in zip(cells, heads.values()):
        years.setdefault(2000 + int(str(h)[-2:]), []).append(c)
    return file, sheet, {y: f"{cs[0]}:{cs[-1]}" for y, cs in years.items()}


def _lease_changeset(rel: str, user: str, on_step) -> ChangeSet | None:
    on_step("Reading the rent terms of the new lease")
    terms = extractor.extract_lease(rel)
    assumption = ex.get("company", "forecast_assumption", "rent_monthly")
    current = float(assumption.value) if assumption else None
    if current is not None and abs(current - terms.rent_monthly) < 0.01:
        return None
    on_step("New rent differs from the forecast assumption → proposing a forecast update")
    forecast, sheet, by_year = _forecast_cells()
    years = sorted(by_year)
    start = terms.rent_from.year
    rent = {
        y: round(terms.rent_monthly * (1 + terms.escalation_pct / 100) ** max(0, y - start), 2)
        for y in years
    }
    y1, y2 = rent[years[0]], rent[years[-1]]
    src = [terms.evidence]
    src_old = [assumption.source] if assumption else []
    signed = f"{terms.signed:%d %b %Y}" if terms.signed else "recently"
    later = ", ".join(f"HK${rent[y]:,.0f} in {y}" for y in years[1:])
    reason = (
        f"New lease {terms.reference or ''} signed {signed}: rent HK${y1:,.0f}/month from "
        f"{terms.rent_from:%d %b %Y}, +{terms.escalation_pct:g}% each January"
        + (f" ({later})" if later else "")
        + (f". Replaces the HK${current:,.0f} flat assumption." if current is not None else ".")
    ).replace("  ", " ")
    changes_: list[CellChange] = []
    for y in years:
        ref = by_year[y]
        first = ref.split(":")[0]
        changes_.append(
            CellChange(
                file=forecast,
                sheet=sheet,
                cell=ref,
                old=sheets.read_range(forecast, sheet, first)[first],
                new=rent[y],
                sources=src,
                reason=reason,
            )
        )
    row = sheets.find_row(forecast, "Assumptions", "rent")
    if row:
        for col, new in (
            (
                "B",
                f"HK${y1:,.0f}/month {years[0]}, +{terms.escalation_pct:g}%/yr (HK${y2:,.0f} {years[-1]})",
            ),
            ("C", f"Lease {terms.reference or rel} p.{terms.evidence.page} cl.4, signed {signed}"),
        ):
            changes_.append(
                CellChange(
                    file=forecast,
                    sheet="Assumptions",
                    cell=f"{col}{row}",
                    old=sheets.read_range(forecast, "Assumptions", f"{col}{row}")[f"{col}{row}"],
                    new=new,
                    sources=src,
                    reason=reason,
                )
            )
    master_row = next((s["_row"] for s in sheets.suppliers() if s["id"] == terms.supplier_id), None)
    if master_row:
        changes_.append(
            CellChange(
                file=MASTER,
                sheet="Suppliers",
                cell=f"I{master_row}",
                old=sheets.read_range(MASTER, "Suppliers", f"I{master_row}")[f"I{master_row}"],
                new=rel,
                sources=src,
                reason=f"New lease replaces the previous lease as the {terms.supplier_id} contract.",
            )
        )
    n_cells = sum(len(sheets.cells_in(by_year[y])) for y in years)
    was = (
        f"Forecast assumes HK${current:,.0f} flat" if current is not None else "No rent assumption"
    )
    cs = ChangeSet(
        id=changes.new_id(),
        title=f"Update rent forecast from new lease ({rel.rsplit('/', 1)[-1]})",
        reason=reason,
        trigger=rel,
        kind="lease",
        changes=changes_,
        findings=[
            Finding(
                control="CONTRACT-001",
                severity="info",
                title="New lease changes the rent forecast",
                detail=(
                    f"Lease: HK${y1:,.0f}/month from {terms.rent_from:%d %b %Y}, +{terms.escalation_pct:g}%/yr. "
                    f"{was}"
                    + (f" ({assumption.note})" if assumption and assumption.note else "")
                    + f". {n_cells} forecast cells would change."
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
    out = [
        Expectation(
            id="E-company-rent-2027",
            subject="company",
            kind="forecast_assumption",
            key="rent_monthly",
            value=y1,
            valid_from=t.rent_from,
            note=f"Rent HK${y1:,.0f}/month from {t.rent_from:%b %Y}, then HK${y2:,.0f} (+{t.escalation_pct:g}%/yr) per new lease",
            source=t.evidence,
        )
    ]
    if t.supplier_id:
        out.append(
            Expectation(
                id=f"E-{t.supplier_id}-recurring-{t.rent_from.year}",
                subject=t.supplier_id,
                kind="recurring_amount",
                value=y1,
                tolerance=0.01,
                valid_from=t.rent_from,
                valid_to=date(t.rent_from.year, 12, 31),
                note=f"Monthly rent HK${y1:,.0f} from {t.rent_from:%b %Y}",
                source=t.evidence,
            )
        )
    return out


# -- questions --------------------------------------------------------------------------------


def _question(cs: ChangeSet) -> Question:
    controls = {f.control for f in cs.findings}
    guarded = controls & GUARDED
    if cs.kind == "lease":
        f = cs.findings[0]
        text = f"{cs.reason} Your forecast still assumes HK${float(f.expected):,.0f} flat. Update the forecast?"
    else:
        text = _llm_question(cs) or _template_question(cs)
    if cs.kind == "email":
        text += (
            " Reject blocks this sender and account in the brain's memory; approve & remember "
            "updates the supplier master (needs a call-back)."
        )
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
