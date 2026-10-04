"""End-to-end pipeline on a temp runtime copy, with a stub LLM returning what a good model would
extract. Checks the planted problems, the register end state and the lease flow vs ground truth."""

import json
from pathlib import Path

import pytest

from app.config import settings
from app.core import changes, decisions, extractor, intake, reader, versioning
from app.core.models import InvoiceLine
from app.data import sheets, workspace

GT = Path("workspace/ground_truth/expected.json")

SCAN_1002 = """珠江成长基金二期 PEARL RIVER GROWTH FUND II LP
缴款通知书 CAPITAL CALL / DRAWDOWN NOTICE
通知编号：PRG2-DN-018  通知日期：2026年9月30日  缴款截止日：2026年10月14日
DD-018 | 第18次缴款 Drawdown No. 18 | 1 | 3,500,000.00
本次应缴金额 合计 人民币（RMB） 3,500,000.00
收款银行：南海联合银行深圳宝安支行  银行账号：6230 5821 4407 7731
如有疑问，请联系 accounts@prg-fund.co"""
SCAN_0930 = """PEAK ESTATES PROPERTY MANAGEMENT LTD  accounts@peakestates.com.hk
INVOICE  INV-PM-2318  Date 30 Sep 2026  Due date 30 Oct 2026
TOTAL HKD 18,500.00"""


def line(code, desc, amount, qty=1, price=None):
    return InvoiceLine(
        item_code=code, description=desc, qty=qty, unit_price=price or amount, amount=amount
    )


RAW = {
    "scan_1002.pdf": dict(
        supplier_name="珠江成长基金二期",
        kind="capital_call",
        invoice_no="PRG2-DN-018",
        invoice_date="2026-09-30",
        due_date="2026-10-14",
        currency="RMB",
        subtotal=3500000,
        tax=0,
        total=3500000,
        bank_account="6230 5821 4407 7731",
        lines=[line("DD-018", "Drawdown No. 18", 3500000)],
    ),
    "HCP3_Capital_Call_Notice_04.pdf": dict(
        supplier_name="Harbourview Capital Partners III LP",
        kind="capital_call",
        invoice_no="HCP3-CN-2026-04",
        invoice_date="2026-09-30",
        due_date="2026-10-10",
        currency="USD",
        subtotal=600000,
        tax=0,
        total=600000,
        bank_account="8841-2207-5530",
        lines=[line("CALL-04", "Capital call 4/2026", 600000)],
    ),
    "HCP3_Q4_2026_Management_Fee.pdf": dict(
        supplier_name="Harbourview Capital Partners III LP",
        kind="fee_notice",
        invoice_no="HCP3-MF-2026Q4",
        invoice_date="2026-10-01",
        due_date="2026-10-31",
        currency="USD",
        subtotal=50000,
        tax=0,
        total=50000,
        bank_account="8841-2207-5530",
        fee_rate_pct=2.0,
        lines=[line("MGMT-FEE", "Management fee Q4 2026", 50000)],
    ),
    "scan_0930_2.pdf": dict(
        supplier_name="Peak Estates Property Management Ltd",
        invoice_no="INV-PM-2318",
        invoice_date="2026-09-30",
        due_date="2026-10-30",
        currency="HKD",
        subtotal=18500,
        tax=0,
        total=18500,
        bank_account="088-221-55190-3",
        lines=[
            line("PM-RB12", "Flat 12A", 8800),
            line("PM-CR21", "Flat 21B", 7600),
            line("KEY-HLD", "Key holding", 900, qty=2, price=450),
            line("LS-INSP", "Inspection", 1200),
        ],
    ),
    "Invoice (3).pdf": dict(
        supplier_name="Peak Estates Property Management Ltd",
        invoice_no="INV-PM-2291-R",
        invoice_date="2026-09-25",
        due_date="2026-10-25",
        currency="HKD",
        subtotal=23200,
        tax=0,
        total=23200,
        lines=[],
        bank_account="088-221-55190-3",
    ),
    "Invoice_MAI-10044.pdf": dict(
        supplier_name="Meridian Fine Art Insurance Ltd",
        invoice_no="MAI-10044",
        invoice_date="2026-10-01",
        due_date="2026-10-16",
        currency="USD",
        subtotal=2450,
        tax=0,
        total=2450,
        lines=[],
        bank_account="4410-0928-1173",
    ),
}
LEASE = dict(
    counterparty="Halcyon Re Asia Ltd",
    reference="LPFO/L/2027/12A",
    signed="2026-09-29",
    rent_monthly=98800,
    rent_from="2027-01-01",
    escalation_pct=3.0,
)


class StubLLM:
    def extract(self, prompt, schema, **kw):
        if schema is extractor._LeaseLLM:
            return schema(**LEASE), None
        name = next(k for k, v in RAW.items() if v["invoice_no"] in prompt)
        return schema(**RAW[name]), None

    def complete(self, *a, **kw):
        raise RuntimeError("offline")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    if not GT.exists():
        pytest.skip("ground truth not generated")
    monkeypatch.setattr(settings, "trace_workspace", str(tmp_path / "ws"))
    monkeypatch.setattr(extractor, "get_llm", lambda: StubLLM())
    monkeypatch.setattr(reader, "_ocr", lambda png: "")
    workspace.reset()
    # simulate the vision OCR output for the two scans
    monkeypatch.setattr(
        reader, "_ocr", lambda png: SCAN_1002 if _current["doc"].endswith("1002.pdf") else SCAN_0930
    )
    return json.loads(GT.read_text())


_current = {"doc": ""}


def test_full_demo_flow(ws, monkeypatch):
    orig = reader.read

    def tracking_read(rel, ocr=True):
        _current["doc"] = rel
        return orig(rel, ocr)

    monkeypatch.setattr(reader, "read", tracking_read)
    css = intake.process_inbox("Jason Yip", print)
    by_doc = {cs.trigger: cs for cs in css}
    assert len(css) == 7  # 6 inbox documents + lease

    # planted problems fire, clean invoices are not held
    fired = {(p["invoice_file"], p["control"]) for p in ws["planted_problems"]}
    got = {(cs.trigger, f.control) for cs in css for f in cs.findings if f.severity == "hold"}
    assert got == fired
    for doc in ws["clean_invoices"]:
        assert by_doc[doc].status == "proposed"
    approvals = {cs.trigger for cs in css for f in cs.findings if f.control == "APPROVAL-001"}
    expected_rows = ws["tasks"][1]["expected"]["rows"]
    assert approvals == {r["source_file"] for r in expected_rows if r["needs_principal_approval"]}

    # policy guard
    s01 = by_doc["docs/invoices/inbox/scan_1002.pdf"]
    with pytest.raises(decisions.PolicyError):
        decisions.decide(s01.id, "approve_and_remember", "looks fine", "Jason Yip")

    # scripted demo: accept clean, reject both held, approve lease
    for doc in ws["clean_invoices"]:
        decisions.accept(by_doc[doc].id, "Jason Yip")
    decisions.decide(
        s01.id, "reject", "Not expected, calling the GP on the number on file", "Jason Yip"
    )
    fee = by_doc["docs/invoices/inbox/HCP3_Q4_2026_Management_Fee.pdf"]
    decisions.decide(fee.id, "reject", "Side letter says 1.50%; asked GP to reissue", "Jason Yip")
    dup = by_doc["docs/invoices/inbox/Invoice (3).pdf"]
    decisions.decide(dup.id, "reject", "Duplicate of INV-PM-2291", "Jason Yip")
    lease = by_doc["docs/contracts/S04_lease_2027_signed.pdf"]
    d, h = decisions.decide(
        lease.id, "approve_and_remember", "Renewal signed by Victoria", "Grace Lam"
    )

    # register end state
    first_new = ws["register_seed_rows"] + 2
    rows = [r for r in sheets.register() if r["_row"] >= first_new]
    expected = expected_rows
    assert len(rows) == len(expected)
    for exp in expected:
        r = next(r for r in rows if r["invoice_no"] == exp["invoice_no"])
        for k in (
            "date",
            "supplier_id",
            "supplier",
            "currency",
            "amount",
            "fx_rate",
            "amount_hkd",
            "account_code",
            "due_date",
            "status",
            "source_file",
        ):
            got_v, exp_v = r[k], exp[k]
            if isinstance(exp_v, float):
                assert abs(float(got_v) - exp_v) < 0.01, (exp["invoice_no"], k, got_v, exp_v)
            else:
                got_s = str(got_v)[:10] if k in ("date", "due_date") else str(got_v)
                assert got_s == str(exp_v), (exp["invoice_no"], k, got_v, exp_v)

    # forecast end state: 24 cells
    task = ws["tasks"][0]["expected"]
    exp_cells = task["cells"]
    for c, v in exp_cells.items():
        got = sheets.read_range(task["file"], task["sheet"], c)[c]
        assert abs(got - v) < 0.01, (c, got, v)

    # blame on the first rent cell: new lease commit and the old rent-flat commit
    first = next(iter(exp_cells))
    hist = versioning.history(task["file"], task["sheet"], first)
    commits = [e["commit"] for e in hist]
    old = ws["tasks"][2]["expected"]["sources"][-1]["commit"]
    assert commits[0] == h and old in commits
    assert hist[0]["sources"][0]["page"] == 3

    # every Trace commit's changed cells have sources with the commit filled in
    assert all(cs.commit for cs in changes.all_changesets() if cs.status != "proposed")
    assert len(workspace.log()) == 10 + 7
