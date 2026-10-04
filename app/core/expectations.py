"""Expectation memory: what the brain expects. Seeded deterministically from the workspace (no LLM);
updated only by decisions."""

import re
from collections import Counter
from datetime import date, datetime

from app.core import reader
from app.core.models import Expectation, SourceRef
from app.data import company, sheets, store

FILE = "expectations.json"
CODE_RE = re.compile(r"^[A-Z]{2,4}-[A-Z0-9]{2,6}$")
PRICE_RE = re.compile(r"^(?:(RMB|USD|HKD)\s)?([\d,]+\.\d{2})$")


def load() -> list[Expectation]:
    return [Expectation.model_validate(e) for e in store.read_json(FILE, [])]


def save(items: list[Expectation]) -> None:
    store.write_json(FILE, [e.model_dump(mode="json") for e in items])


def get(
    subject: str, kind: str, key: str | None = None, on: date | None = None
) -> Expectation | None:
    """Latest matching expectation valid on `on` (learned ones win over seeded)."""
    hits = [
        e
        for e in load()
        if e.subject == subject
        and e.kind == kind
        and (key is None or e.key == key)
        and (on is None or e.valid_from is None or e.valid_from <= on)
        and (on is None or e.valid_to is None or on <= e.valid_to)
    ]
    hits.sort(key=lambda e: (e.learned_from is not None, e.valid_from or date.min))
    return hits[-1] if hits else None


def upsert(new: list[Expectation]) -> None:
    items = {e.id: e for e in load()}
    for e in new:
        items[e.id] = e
    save(list(items.values()))


def _price_schedule(doc: str, supplier_id: str, ccy: str) -> list[Expectation]:
    out = []
    for page in reader.read(doc, ocr=False).pages:
        lines = [ln.strip() for ln in page.text.splitlines()]
        for i, ln in enumerate(lines):
            if not CODE_RE.match(ln):
                continue
            for nxt in lines[i + 1 : i + 5]:
                if m := PRICE_RE.match(nxt):
                    price = float(m.group(2).replace(",", ""))
                    clause = _clause_before(lines[:i])
                    out.append(
                        Expectation(
                            id=f"E-{supplier_id}-price-{ln}",
                            subject=supplier_id,
                            kind="unit_price",
                            key=ln,
                            value=price,
                            note=f"{m.group(1) or ccy} {price:,.2f} per unit",
                            source=SourceRef(doc=doc, page=page.page, quote=nxt, clause=clause),
                        )
                    )
                    break
    return out


def _clause_before(lines: list[str]) -> str | None:
    """Nearest clause / schedule heading above a price table, e.g. '4.2' or 'Schedule 1'."""
    for ln in reversed(lines):
        if m := re.match(r"^(\d+\.\d+)\s", ln):
            return m.group(1)
        if m := re.match(r"^(Schedule \d+)", ln):
            return m.group(1)
    return None


def _contract_terms(doc: str, supplier_id: str) -> list[Expectation]:
    text = reader.read(doc, ocr=False).text
    out = []
    m = re.search(r"Renewal date\s*\n?\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    n = re.search(r"at least (\d+) days before the Renewal Date", text)
    if m and n:
        renewal = datetime.strptime(m.group(1), "%B %d, %Y").date()
        out.append(
            Expectation(
                id=f"E-{supplier_id}-renewal",
                subject=supplier_id,
                kind="contract_term",
                key="auto_renewal",
                value=renewal.isoformat(),
                note=f"Auto-renews {renewal:%d %b %Y}; {n.group(1)} days' notice to cancel",
                tolerance=float(n.group(1)),  # notice days
                source=SourceRef(doc=doc, page=1, quote=n.group(0)),
            )
        )
    return out


def _fee_rate(doc: str, supplier_id: str) -> list[Expectation]:
    """Side letter / LPA: 'calculated at the rate of 1.50% per annum' -> fee_rate expectation."""
    for page in reader.read(doc, ocr=False).pages:
        flat = _flat(page.text)
        m = re.search(r"fee[^.]*?rate of (\d+(?:\.\d+)?)% per annum", flat, re.I)
        if m:
            nums = re.findall(r"(?:^|\n)(\d+\.\d+)\n", page.text[: page.text.find("rate of")])
            clause = nums[-1] if nums else None
            return [
                Expectation(
                    id=f"E-{supplier_id}-fee-rate",
                    subject=supplier_id,
                    kind="fee_rate",
                    key="management_fee",
                    value=float(m.group(1)),
                    note=f"Management fee {float(m.group(1)):.2f}% a year",
                    source=SourceRef(
                        doc=doc,
                        page=page.page,
                        quote=f"rate of {m.group(1)}% per annum",
                        clause=clause,
                    ),
                )
            ]
    return []


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _company() -> list[Expectation]:
    """Policies, approval rule, account conventions and forecast assumptions from COMPANY.md."""
    doc, text = "COMPANY.md", company.text()
    flat = _flat(text)
    items: list[Expectation] = []
    if m := re.search(r"by more than (\d+(?:\.\d+)?)%", flat):
        items.append(
            Expectation(
                id="E-company-tolerance",
                subject="company",
                kind="price_tolerance",
                value=float(m.group(1)) / 100,
                note=f"Unit prices and fee rates may exceed the contract by at most {m.group(1)}%",
                source=SourceRef(doc=doc, quote=m.group(0)),
            )
        )
    person, limit, line = company.approver()
    if limit:
        items.append(
            Expectation(
                id="E-company-approval",
                subject="company",
                kind="approval_limit",
                key=company.short(person),
                value=limit,
                note=f"Anything above HK${limit:,.0f} needs {company.short(person)}'s approval",
                source=SourceRef(doc=doc, quote=line),
            )
        )
    for kind, label in (
        ("capital_call", "capital calls"),
        ("fee_notice", "fund management fee notices"),
    ):
        if m := re.search(rf"{label} -> (\d{{3}})", flat, re.I):
            items.append(
                Expectation(
                    id=f"E-company-account-{kind}",
                    subject="company",
                    kind="account_code",
                    key=kind,
                    value=m.group(1),
                    note=f"{label.capitalize()} are booked to account {m.group(1)}",
                    source=SourceRef(doc=doc, quote=m.group(0)),
                )
            )
    for line in text.splitlines():
        m = re.search(r"assumed flat at HK\$([\d,]+)", line)
        if m and "rent" in line.lower():
            items.append(
                Expectation(
                    id="E-company-rent-2027",
                    subject="company",
                    kind="forecast_assumption",
                    key="rent_monthly",
                    value=float(m.group(1).replace(",", "")),
                    valid_from=date(2027, 1, 1),
                    note=line.lstrip("- ").strip(),
                    source=SourceRef(doc=doc, quote=line.lstrip("- ").strip()),
                )
            )
            break
    return items


def seed() -> list[Expectation]:
    items = _company()
    register = sheets.register()
    for s in sheets.suppliers():
        sid = s["id"]
        master = SourceRef(doc="sheets/supplier_master.xlsx", quote=f"{sid} row {s['_row']}")
        items.append(
            Expectation(
                id=f"E-{sid}-bank",
                subject=sid,
                kind="bank_account",
                value=s["bank_account"],
                note=s["bank_name"],
                source=master,
            )
        )
        items.append(
            Expectation(
                id=f"E-{sid}-domain",
                subject=sid,
                kind="email_domain",
                value=s["email_domain"],
                source=master,
            )
        )
        rows = [r for r in register if r["supplier_id"] == sid]
        if rows:
            code = Counter(str(r["account_code"]) for r in rows).most_common(1)[0][0]
            items.append(
                Expectation(
                    id=f"E-{sid}-account",
                    subject=sid,
                    kind="account_code",
                    value=code,
                    source=SourceRef(
                        doc="sheets/invoice_register.xlsx", quote=f"{len(rows)} past invoices"
                    ),
                )
            )
            amount, count = Counter(float(r["amount"]) for r in rows).most_common(1)[0]
            if count >= 3:
                items.append(
                    Expectation(
                        id=f"E-{sid}-recurring",
                        subject=sid,
                        kind="recurring_amount",
                        value=amount,
                        tolerance=0.01,
                        note=f"{s['currency']} {amount:,.2f} seen {count} times",
                        source=SourceRef(
                            doc="sheets/invoice_register.xlsx", quote=f"{count} invoices"
                        ),
                    )
                )
        doc = s["contract_file"]
        if doc and reader.can_read(doc):
            items += _price_schedule(doc, sid, s["currency"])
            items += _fee_rate(doc, sid)
            items += _contract_terms(doc, sid)
    save(items)
    return items


def contract_deadlines(today: date, within_days: int = 30) -> list[dict]:
    """Auto-renewing contracts whose cancellation deadline falls in the window (computed in code)."""
    from datetime import timedelta

    out = []
    for e in load():
        if e.kind != "contract_term" or e.key != "auto_renewal":
            continue
        renewal = date.fromisoformat(str(e.value))
        notice = int(e.tolerance or 0)
        deadline = renewal - timedelta(days=notice)
        if today <= deadline <= today + timedelta(days=within_days):
            recurring = get(e.subject, "recurring_amount")
            out.append(
                dict(
                    supplier_id=e.subject,
                    contract=e.source.doc,
                    renewal_date=renewal.isoformat(),
                    notice_days=notice,
                    notice_deadline=deadline.isoformat(),
                    monthly=float(recurring.value) if recurring else None,
                    source=e.source,
                )
            )
    return out
