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

SCAN_1002 = """深圳市零件有限公司 Shenzhen Parts Co., Ltd.
增值税发票 INVOICE  No. SP-2026-0917  日期 Date: 2026-09-30
SP-4410 | 电源管理模块 | 2,000 | 118.00 | 236,000.00
SP-2208 | USB-C连接器组件 | 3,000 | 23.50 | 70,500.00
价税合计 Total RMB 306,500.00
收款银行 南海联合银行深圳宝安支行 账号 6230 5821 4407 7731
联系 accounts@shenzhen-parts.co"""
SCAN_0930 = """PACIFIC FREIGHT LOGISTICS LTD  billing@pacfreight.com.hk
INVOICE  INV-2318  Date 30 Sep 2026  Due 30 Oct 2026
TOTAL HKD 33,900.00"""

RAW = {
    "scan_1002.pdf": dict(
        supplier_name="深圳市零件有限公司",
        invoice_no="SP-2026-0917",
        invoice_date="2026-09-30",
        currency="RMB",
        subtotal=306500,
        tax=0,
        total=306500,
        bank_account="6230 5821 4407 7731",
        lines=[
            InvoiceLine(
                item_code="SP-4410", description="IC", qty=2000, unit_price=118, amount=236000
            ),
            InvoiceLine(
                item_code="SP-2208", description="USB-C", qty=3000, unit_price=23.5, amount=70500
            ),
        ],
    ),
    "DPE-INV-0388.pdf": dict(
        supplier_name="Dongguan Precision Electronics Co., Ltd.",
        invoice_no="DPE/INV/0388",
        invoice_date="2026-09-30",
        due_date="2026-10-30",
        currency="USD",
        subtotal=35350,
        tax=0,
        total=35350,
        bank_account="7800 1123 4588 0062",
        lines=[
            InvoiceLine(
                item_code="DPE-PCB6", description="PCB", qty=1500, unit_price=14.2, amount=21300
            ),
            InvoiceLine(
                item_code="DPE-ENC1", description="Enc", qty=1000, unit_price=6.85, amount=6850
            ),
            InvoiceLine(
                item_code="DPE-CBL12", description="Cbl", qty=3000, unit_price=2.4, amount=7200
            ),
        ],
    ),
    "scan_0930_2.pdf": dict(
        supplier_name="Pacific Freight Logistics Ltd",
        invoice_no="INV-2318",
        invoice_date="2026-09-30",
        due_date="2026-10-30",
        currency="HKD",
        subtotal=33900,
        tax=0,
        total=33900,
        lines=[],
        bank_account="088-221-55190-3",
    ),
    "Invoice (3).pdf": dict(
        supplier_name="Pacific Freight Logistics Ltd",
        invoice_no="INV-2291-R",
        invoice_date="2026-09-25",
        due_date="2026-10-25",
        currency="HKD",
        subtotal=27660,
        tax=0,
        total=27660,
        lines=[],
        bank_account="088-221-55190-3",
    ),
    "Invoice_CD-10044.pdf": dict(
        supplier_name="CloudDesk Inc.",
        invoice_no="CD-10044",
        invoice_date="2026-10-01",
        due_date="2026-10-16",
        currency="USD",
        subtotal=1450,
        tax=0,
        total=1450,
        lines=[],
        bank_account="4410-0928-1173",
    ),
}
LEASE = dict(
    reference="KBP/L/2027/09A",
    signed="2026-09-29",
    rent_monthly=82400,
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
    css = intake.process_inbox("Ken Lau", print)
    by_doc = {cs.trigger: cs for cs in css}
    assert len(css) == 6  # 5 invoices + lease

    # planted problems fire, clean invoices are not held
    fired = {(p["invoice_file"], p["control"]) for p in ws["planted_problems"]}
    got = {(cs.trigger, f.control) for cs in css for f in cs.findings if f.severity == "hold"}
    assert got == fired
    for doc in ws["clean_invoices"]:
        assert by_doc[doc].status == "proposed"
    approvals = {cs.trigger for cs in css for f in cs.findings if f.control == "APPROVAL-001"}
    assert approvals == {
        "docs/invoices/inbox/DPE-INV-0388.pdf",
        "docs/invoices/inbox/scan_1002.pdf",
    }

    # policy guard
    s01 = by_doc["docs/invoices/inbox/scan_1002.pdf"]
    with pytest.raises(decisions.PolicyError):
        decisions.decide(s01.id, "approve_and_remember", "looks fine", "Ken Lau")

    # scripted demo: accept clean, reject both held, approve lease
    for doc in ws["clean_invoices"]:
        decisions.accept(by_doc[doc].id, "Ken Lau")
    decisions.decide(s01.id, "reject", "Not expected, calling supplier on known number", "Ken Lau")
    dup = by_doc["docs/invoices/inbox/Invoice (3).pdf"]
    decisions.decide(dup.id, "reject", "Duplicate of INV-2291", "Ken Lau")
    lease = by_doc["docs/contracts/S04_lease_2027_signed.pdf"]
    d, h = decisions.decide(lease.id, "approve_and_remember", "Lease signed by David", "Anna Chan")

    # register end state
    rows = [r for r in sheets.register() if r["_row"] >= 19]
    expected = ws["tasks"][1]["expected"]["rows"]
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
    cells = sheets.read_range("sheets/forecast_2027_2028.xlsx", "Forecast", "C9:Z9")
    for c, v in ws["tasks"][0]["expected"]["cells"].items():
        assert abs(cells[c] - v) < 0.01, (c, cells[c], v)

    # blame on C9: new lease commit and the old rent-flat commit
    hist = versioning.history("sheets/forecast_2027_2028.xlsx", "Forecast", "C9")
    commits = [e["commit"] for e in hist]
    assert commits[0] == h and any(c.startswith("cbcb6ff") for c in commits)
    assert hist[0]["sources"][0]["page"] == 3

    # every Trace commit's changed cells have sources with the commit filled in
    assert all(cs.commit for cs in changes.all_changesets() if cs.status != "proposed")
    assert len(workspace.log()) == 10 + 6
