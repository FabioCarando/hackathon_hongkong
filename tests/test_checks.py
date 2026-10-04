"""Deterministic controls on hand-built documents (no LLM): the fee-rate check under PRICE-001."""

from datetime import date
from pathlib import Path

import pytest

from app.config import settings
from app.core import checks
from app.core.models import InvoiceData
from app.data import workspace


@pytest.fixture
def ws(tmp_path, monkeypatch):
    if not Path("workspace/COMPANY.md").exists():
        pytest.skip("workspace not generated")
    monkeypatch.setattr(settings, "trace_workspace", str(tmp_path / "ws"))
    workspace.reset()


def fee_notice(rate: float, total: float) -> InvoiceData:
    return InvoiceData(
        supplier_name="Harbourview Capital Partners III LP",
        supplier_id="S02",
        kind="fee_notice",
        invoice_no="HCP3-MF-TEST",
        invoice_date=date(2026, 10, 1),
        currency="USD",
        subtotal=total,
        total=total,
        bank_account="8841-2207-5530",
        fee_rate_pct=rate,
    )


def test_fee_rate_above_side_letter_is_held(ws):
    found = [f for f in checks.run(fee_notice(2.0, 50000)) if f.control == "PRICE-001"]
    assert len(found) == 1
    f = found[0]
    assert f.severity == "hold" and f.expected == 1.5 and f.actual == 2.0
    assert "12,500.00" in f.detail  # overcharge = 50,000 x (1 - 1.5 / 2.0)
    assert f.evidence[-1].doc == "docs/contracts/S02_side_letter_2024.pdf"


def test_fee_rate_at_side_letter_passes(ws):
    assert not [f for f in checks.run(fee_notice(1.5, 37500)) if f.severity == "hold"]


def test_approval_limit_comes_from_company_md(ws):
    big = fee_notice(1.5, 37500).model_copy(update={"total": 600000.0, "fee_rate_pct": None})
    approval = [f for f in checks.run(big) if f.control == "APPROVAL-001"]
    assert approval and approval[0].title == "Needs V. Cheung approval"
    assert approval[0].expected == 500000.0
