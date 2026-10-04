"""Pydantic models: the contracts between Trace modules (spec/03-architecture.md)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    doc: str | None = None  # workspace-relative path
    page: int | None = None  # 1-based
    quote: str | None = None  # exact text from the document
    clause: str | None = None
    commit: str | None = None  # when the source is a past commit
    decision: str | None = None  # when the source is a decision ID, e.g. "D-0003"

    def label(self) -> str:
        if self.decision:
            return self.decision
        if self.commit and not self.doc:
            return self.commit[:7]
        name = (self.doc or "").rsplit("/", 1)[-1]
        if self.page:
            name += f" p.{self.page}"
        if self.clause:
            name += f" §{self.clause}"
        return name


DocKind = Literal[
    "invoice", "contract", "bank_statement", "email", "sheet", "ledger", "memory", "other"
]


class FileEntry(BaseModel):
    path: str
    kind: DocKind
    sha256: str
    size: int
    pages: int | None = None
    supplier_id: str | None = None
    title: str
    status: Literal["new", "read", "processed", "held", "tracked"]
    text_method: Literal["text_layer", "vision_ocr", "native", "none"] = "none"
    last_commit: str | None = None
    used_in: list[str] = []


class PageText(BaseModel):
    page: int
    text: str
    method: Literal["text_layer", "vision_ocr", "native"]


class ReadResult(BaseModel):
    path: str
    sha256: str
    pages: list[PageText]

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


class InvoiceLine(BaseModel):
    item_code: str | None = None
    description: str
    qty: float
    unit_price: float
    amount: float


class InvoiceData(BaseModel):
    supplier_name: str
    supplier_id: str | None = None  # matched in code against supplier_master, never by the LLM
    kind: Literal["invoice", "capital_call", "fee_notice"] = "invoice"
    invoice_no: str
    invoice_date: date
    due_date: date | None = None
    currency: Literal["HKD", "RMB", "USD"]
    lines: list[InvoiceLine] = []
    subtotal: float
    tax: float = 0.0
    total: float
    bank_account: str | None = None
    fee_rate_pct: float | None = None  # yearly fee rate printed on a fee notice, e.g. 2.0
    sender_emails: list[str] = []  # found in code: invoice text + linked emails
    evidence: dict[str, SourceRef] = {}  # field name -> where it was read
    problems: list[str] = []  # code validation failures ("needs review")


class LeaseTerms(BaseModel):
    supplier_id: str | None = None
    reference: str | None = None
    signed: date | None = None
    rent_monthly: float
    rent_from: date
    escalation_pct: float
    evidence: SourceRef


class EmailData(BaseModel):
    sender: str  # address from the From header
    sender_name: str | None = None
    subject: str
    received: datetime | None = None
    claimed_supplier: str | None = None  # who the email says it is from
    supplier_id: str | None = None  # matched in code
    request: Literal["bank_change", "payment_request", "other"]
    new_bank_account: str | None = None
    bank_name: str | None = None
    invoice_refs: list[str] = []
    summary: str = ""
    evidence: dict[str, SourceRef] = {}


class Expectation(BaseModel):
    id: str
    subject: str  # supplier_id or "company"
    kind: Literal[
        "unit_price",
        "fee_rate",
        "bank_account",
        "email_domain",
        "recurring_amount",
        "approval_limit",
        "price_tolerance",
        "forecast_assumption",
        "contract_term",
        "account_code",
        "blocked_sender",  # learned from a rejected fraud attempt
        "blocked_bank",
    ]
    key: str | None = None
    value: str | float
    tolerance: float | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    note: str | None = None
    source: SourceRef
    learned_from: str | None = None  # decision ID if it was learned


class Finding(BaseModel):
    control: str  # "PRICE-001", ...
    severity: Literal["hold", "flag", "approval", "info"]  # flag = enter, but block payment
    title: str  # plain language
    detail: str
    expected: str | float | None = None
    actual: str | float | None = None
    evidence: list[SourceRef] = []
    expectation_id: str | None = None


class CellChange(BaseModel):
    file: str
    sheet: str
    cell: str  # "C9" or a range "C9:N9"
    old: str | float | None = None
    new: str | float | None = None
    sources: list[SourceRef] = []
    reason: str


class NewRow(BaseModel):
    """A row appended at accept time (row number is assigned then)."""

    file: str
    sheet: str
    values: dict[str, date | float | str | None]  # column header -> value
    sources: list[SourceRef] = []
    reason: str


Answer = Literal["reject", "approve_once", "approve_and_remember"]


class Question(BaseModel):
    text: str
    options: list[Answer]
    blocked_options_reason: str | None = None


class ChangeSet(BaseModel):
    id: str  # "CS-0001"
    title: str
    reason: str
    trigger: str  # doc path
    kind: Literal["invoice", "lease", "email"]
    changes: list[CellChange] = []
    new_rows: list[NewRow] = []
    findings: list[Finding] = []
    question: Question | None = None
    status: Literal["proposed", "held", "accepted", "rejected"]
    created_by: str
    created_at: datetime
    decided_by: str | None = None
    decision: str | None = None
    commit: str | None = None
    invoice: InvoiceData | None = None
    payment_blocked: bool = False  # entered with a flag until a call-back clears it
    lease: LeaseTerms | None = None
    email: EmailData | None = None
    memory_updates: list[Expectation] = []  # applied on approve_and_remember
    reject_memory: list[Expectation] = []  # applied on reject (e.g. block a fraud bank account)


class Decision(BaseModel):
    id: str  # "D-0001"
    at: datetime
    by: str
    changeset_id: str
    answer: Answer
    reason: str
    findings: list[str] = []
    memory_updates: list[str] = Field(default_factory=list)  # expectation IDs
    commit: str | None = None
