"""Deterministic controls: invoice data vs expectations. No LLM here: code decides."""

import re
from datetime import date

from app.core import expectations as ex
from app.core.models import Finding, InvoiceData, SourceRef
from app.data import sheets


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _norm_no(no: str) -> str:
    s = no.upper().strip()
    s = re.sub(r"\s*\((COPY|DUPLICATE|REISSUE)\)$", "", s)
    s = re.sub(r"[-/ ](R|REV|COPY|DUP)\d*$", "", s)
    return re.sub(r"[\s]", "", s)


def amount_hkd(inv: InvoiceData) -> float:
    return round(inv.total * sheets.fx_rate(inv.currency, inv.invoice_date), 2)


def check_unknown(inv: InvoiceData) -> list[Finding]:
    if inv.supplier_id:
        return []
    return [
        Finding(
            control="UNKNOWN-001",
            severity="hold",
            title="Counterparty not on the master list",
            detail=f"'{inv.supplier_name}' does not match any known counterparty.",
            actual=inv.supplier_name,
        )
    ]


def _tolerance() -> float:
    tol = ex.get("company", "price_tolerance")
    return float(tol.value) if tol else 0.01


def check_fee_rate(inv: InvoiceData) -> list[Finding]:
    """PRICE-001 for fee notices: the fee rate charged vs the contract / side-letter rate."""
    if inv.fee_rate_pct is None:
        return []
    e = ex.get(inv.supplier_id, "fee_rate", on=inv.invoice_date)
    if not e:
        return []
    tolerance, expected, rate = _tolerance(), float(e.value), inv.fee_rate_pct
    if rate <= expected * (1 + tolerance) + 1e-9:
        return []
    pct = (rate / expected - 1) * 100
    extra = inv.total * (1 - expected / rate)
    return [
        Finding(
            control="PRICE-001",
            severity="hold",
            title=f"Fee rate {pct:.0f}% above the agreed rate",
            detail=(
                f"Charged at {rate:.2f}% a year vs {expected:.2f}% in {e.source.label()} "
                f"(+{pct:.1f}%, tolerance {tolerance:.0%}). Overcharge {inv.currency} {extra:,.2f}: "
                f"should be {inv.currency} {inv.total - extra:,.2f}, not {inv.total:,.2f}."
            ),
            expected=expected,
            actual=rate,
            evidence=[r for r in (inv.evidence.get("fee_rate"), e.source) if r],
            expectation_id=e.id,
        )
    ]


def check_price(inv: InvoiceData) -> list[Finding]:
    tolerance = _tolerance()
    out = []
    for ln in inv.lines:
        if not ln.item_code:
            continue
        e = ex.get(inv.supplier_id, "unit_price", ln.item_code, inv.invoice_date)
        if not e:
            continue
        expected = float(e.value)
        if ln.unit_price > expected * (1 + tolerance) + 1e-9:
            pct = (ln.unit_price / expected - 1) * 100
            extra = (ln.unit_price - expected) * ln.qty
            out.append(
                Finding(
                    control="PRICE-001",
                    severity="hold",
                    title=f"Price {pct:.1f}% above contract",
                    detail=(
                        f"{ln.item_code}: {inv.currency} {ln.unit_price:,.2f}/unit vs "
                        f"{inv.currency} {expected:,.2f} in {e.source.label()} (+{pct:.2f}%, "
                        f"tolerance {tolerance:.0%}). Overcharge {inv.currency} {extra:,.2f} on "
                        f"{ln.qty:,.0f} units."
                    ),
                    expected=expected,
                    actual=ln.unit_price,
                    evidence=[r for r in (inv.evidence.get(f"line:{ln.item_code}"), e.source) if r],
                    expectation_id=e.id,
                )
            )
    return out


def check_bank(inv: InvoiceData) -> list[Finding]:
    e = ex.get(inv.supplier_id, "bank_account")
    if not e or not inv.bank_account:
        return []
    if _digits(inv.bank_account) == _digits(str(e.value)):
        return []
    paid = [
        p
        for p in sheets_payments()
        if p["supplier_id"] == inv.supplier_id
        and _digits(p["bank_account_paid"]) == _digits(str(e.value))
    ]
    history = (
        f" The last {len(paid)} payments went to …{_digits(str(e.value))[-4:]}." if paid else ""
    )
    return [
        Finding(
            control="BANK-001",
            severity="hold",
            title="Bank account changed",
            detail=(
                f"Invoice asks for payment to …{_digits(inv.bank_account)[-4:]} "
                f"({inv.bank_account}); the counterparty master has …{_digits(str(e.value))[-4:]}.{history}"
            ),
            expected=str(e.value),
            actual=inv.bank_account,
            evidence=[r for r in (inv.evidence.get("bank_account"), e.source) if r],
            expectation_id=e.id,
        )
    ]


def check_domain(inv: InvoiceData) -> list[Finding]:
    e = ex.get(inv.supplier_id, "email_domain")
    if not e:
        return []
    known = str(e.value).lower()
    bad = [m for m in inv.sender_emails if not m.lower().split("@")[1].endswith(known)]
    if not bad:
        return []
    domains = sorted({m.split("@")[1] for m in bad})
    return [
        Finding(
            control="DOMAIN-001",
            severity="hold",
            title="Sent from a lookalike domain",
            detail=f"Contact/sender domain {', '.join(domains)} is not the known domain {known}.",
            expected=known,
            actual=", ".join(domains),
            evidence=[r for m in bad if (r := inv.evidence.get(f"email:{m}"))] + [e.source],
            expectation_id=e.id,
        )
    ]


def check_duplicate(inv: InvoiceData) -> list[Finding]:
    out = []
    for r in sheets.register():
        if r["supplier_id"] != inv.supplier_id:
            continue
        same_no = _norm_no(str(r["invoice_no"])) == _norm_no(inv.invoice_no)
        r_date = date.fromisoformat(str(r["date"])[:10])
        same_amt = (
            abs(float(r["amount"]) - inv.total) < 0.01
            and abs((r_date - inv.invoice_date).days) <= 7
        )
        if same_no or same_amt:
            why = "same invoice number" if same_no else "same amount within 7 days"
            out.append(
                Finding(
                    control="DUP-001",
                    severity="hold",
                    title="Looks like a duplicate",
                    detail=(
                        f"Same as {r['invoice_no']} dated {r_date:%d %b %Y} ({why}), "
                        f"{r['currency']} {float(r['amount']):,.2f}, already in the register "
                        f"(row {r['_row']}, status {r['status']})."
                    ),
                    expected=None,
                    actual=inv.invoice_no,
                    evidence=[
                        x
                        for x in (
                            inv.evidence.get("invoice_no"),
                            SourceRef(
                                doc="sheets/invoice_register.xlsx",
                                quote=f"Register row {r['_row']}",
                            ),
                            SourceRef(doc=r["source_file"]) if r.get("source_file") else None,
                        )
                        if x
                    ],
                )
            )
    return out


def check_approval(inv: InvoiceData) -> list[Finding]:
    e = ex.get("company", "approval_limit")
    if not e:
        return []
    limit = float(e.value)
    hkd = amount_hkd(inv)
    if hkd <= limit:
        return []
    return [
        Finding(
            control="APPROVAL-001",
            severity="approval",
            title=f"Needs {e.key or 'director'} approval",
            detail=f"HK${hkd:,.2f} is above the HK${limit:,.0f} approval limit.",
            expected=limit,
            actual=hkd,
            evidence=[e.source],
            expectation_id=e.id,
        )
    ]


def sheets_payments() -> list[dict]:
    import csv

    from app.data import workspace

    with open(workspace.path("ledger/payments_history.csv"), newline="") as f:
        return list(csv.DictReader(f))


CONTROLS = [
    check_unknown,
    check_price,
    check_fee_rate,
    check_bank,
    check_domain,
    check_duplicate,
    check_approval,
]


def run(inv: InvoiceData) -> list[Finding]:
    return [f for c in CONTROLS for f in c(inv)]
