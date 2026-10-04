# 03 · Architecture

## Principles

1. **Copy what makes coding agents trustworthy.** Reads are free. Every write is a proposed change set (a diff) that a human accepts. Accepting creates a git commit whose message is the reason, plus per-cell sources.
2. **The LLM reads, extracts, explains and asks. Code decides.** All checks against expectations are deterministic Python. The LLM never decides whether money is at risk and never does arithmetic that lands in a sheet.
3. **Every value has a source.** Nothing reaches a sheet without `{doc, page, quote}` or a decision ID behind it.
4. **Memory is data, not prompt.** Expectations and decisions live in JSON files the code checks against. The LLM sees them as context but doesn't own them.
5. **Offline-safe demo.** OCR and extraction results are cached by file hash. The LLM disk cache (`LLM_CACHE=on`) covers the rest.

## Overview

```
                     ┌──────────────────── Streamlit UI (05-ui.md) ────────────────────┐
                     │ Inbox · Files · Memory · History · Ask                           │
                     └───────┬───────────────┬───────────────┬──────────────┬───────────┘
                             ▼               ▼               ▼              ▼
  workspace files ──► INDEXER ──► READER (OCR) ──► EXTRACTOR ──► CHECKS ──► QUESTIONS
  (runtime copy)      catalog      text layer or     pydantic       deterministic   ask user why
                      + hashes     vision LLM        fields+quotes  vs expectations      │
                                                                         │               ▼
                                                                         ▼          DECISIONS ──► EXPECTATIONS
                                                                   CHANGE SET             (log)        (memory)
                                                                   proposed cells
                                                                         │ human accepts
                                                                         ▼
                                                                   WRITER (openpyxl) ──► VERSIONING (git commit
                                                                                          + sources.json)
  ASK agent (run_agent) ── tools: search · read_document · read_sheet · cell_history · decisions · expectations
```

## Code layout

New code goes in `app/core/` (domain), `app/data/` (storage/IO) and `app/ui/views/` (pages). Keep each module small.

```
app/
  config.py                 + trace_workspace, trace_seed_workspace, llm_model_vision (see Settings below)
  llm/openrouter.py         + image content blocks → OpenAI image_url (see LLM)
  data/
    workspace.py            runtime copy: reset(), path helpers, git() wrapper, users()
    company.py              facts read from COMPANY.md: name, people, email domain, approver, forecast named range
    store.py                JSON/JSONL read/write for .trace/* files (atomic writes)
    sheets.py               read_sheet / write_cells / append_rows with openpyxl (keep formatting, formulas)
  core/
    models.py               all pydantic models below (the contract between modules)
    indexer.py              scan workspace → FileEntry catalog
    reader.py               document → pages of text (text layer, else vision OCR); cached by sha256
    extractor.py            text → InvoiceData / ContractData / EmailData via llm.extract, with quotes
    expectations.py         seed from workspace; load/save; update from decisions
    checks.py               deterministic controls → Finding list
    intake.py               orchestrates: read → extract → check → ChangeSet (+ Questions)
    changes.py              ChangeSet apply / reject; writes sheets; calls versioning
    versioning.py           git commit, sources.json append, history/blame lookup
    decisions.py            record answers, apply memory updates (respecting policy)
    ask.py                  "Ask the brain" agent + citation validator
    search.py               TF-IDF search over extracted text (scikit-learn)
  ui/views/
    inbox.py  files.py  memory.py  history.py  ask.py
scripts/
  eval.py                   runs the pipeline against ground_truth/expected.json (06)
  seed_brain.py             builds index + expectations for the runtime workspace (also callable from UI)
tests/
  test_checks.py  test_versioning.py  test_intake_fake.py
```

## Storage

### Runtime copy (important)

`workspace/` is tracked by the outer repo and must stay pristine. The app works on a **runtime copy**:

- `TRACE_WORKSPACE` (default `runtime/workspace`, git-ignored): where the app reads and writes.
- `TRACE_SEED_WORKSPACE` (default `workspace`): the pristine source.
- `workspace.reset()` deletes the runtime copy and copies the seed (including `.trace/git`, then fixes `core.worktree` to the new path). The UI has a **"Reset demo"** button in the sidebar.
- Add `runtime/` to the outer `.gitignore`.

### Files Trace owns (inside the runtime workspace)

| Path | Format | Content |
|---|---|---|
| `.trace/git/` | git | Version history of the workspace (already seeded with 10 commits) |
| `.trace/sources.json` | JSON list | Per-cell provenance (schema in `02`). Append on every accepted change |
| `.trace/index.json` | JSON | `FileEntry` catalog |
| `.trace/extracted/<sha256>.json` | JSON | `ReadResult` + extracted structured data per document (OCR cache) |
| `.trace/expectations.json` | JSON list | `Expectation` records |
| `.trace/decisions.jsonl` | JSONL | `Decision` records, append-only |
| `.trace/changesets/<id>.json` | JSON | `ChangeSet` records (proposed / accepted / rejected / held) |

`.trace/` metadata files (except `git/`) are committed along with the sheet changes, so history covers memory too.

Git calls: `subprocess.run(["git", f"--git-dir={ws}/.trace/git", f"--work-tree={ws}", ...])`. Commit author = the current user (sidebar selector: the people listed in COMPANY.md, emails `first.last@<Email domain>` from COMPANY.md; see `app/data/company.py`). Use `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` = real now. No GitPython needed.

## Data models (`app/core/models.py`)

These are the contracts between modules. Keep names and fields; add fields if needed.

```python
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field

class SourceRef(BaseModel):
    doc: str                         # workspace-relative path, e.g. "docs/contracts/S04_lease_2027_signed.pdf"
    page: int | None = None          # 1-based
    quote: str | None = None         # exact text from the document
    clause: str | None = None
    commit: str | None = None        # when the source is a past commit
    decision: str | None = None      # when the source is a decision ID, e.g. "D-0003"

DocKind = Literal["invoice", "contract", "bank_statement", "email", "sheet", "ledger", "memory", "other"]

class FileEntry(BaseModel):
    path: str
    kind: DocKind
    sha256: str
    size: int
    pages: int | None = None
    supplier_id: str | None = None
    title: str                       # human label, e.g. "Pearl River capital call PRG2-DN-018"
    status: Literal["new", "read", "processed", "held", "tracked"]
    text_method: Literal["text_layer", "vision_ocr", "native", "none"] = "none"
    language: str | None = None      # "en", "zh", "en+zh"
    first_seen: datetime
    last_commit: str | None = None   # last commit touching this file
    used_in: list[str] = []          # cells/rows that cite this doc: "sheets/invoice_register.xlsx!Register!F19"

class PageText(BaseModel):
    page: int
    text: str
    method: Literal["text_layer", "vision_ocr"]

class ReadResult(BaseModel):
    path: str
    sha256: str
    pages: list[PageText]

class Field_(BaseModel):            # one extracted value with its evidence
    value: str | float | None
    page: int | None = None
    quote: str | None = None

class InvoiceLine(BaseModel):
    item_code: str | None
    description: str
    qty: float
    unit_price: float
    amount: float

class InvoiceData(BaseModel):
    supplier_name: str
    supplier_id: str | None          # matched by code against supplier_master, not by the LLM
    kind: Literal["invoice", "capital_call", "fee_notice"] = "invoice"   # LLM classifies
    invoice_no: str
    invoice_date: date
    due_date: date | None
    currency: Literal["HKD", "RMB", "USD"]
    lines: list[InvoiceLine]
    subtotal: float
    tax: float
    total: float
    bank_account: str | None
    fee_rate_pct: float | None       # yearly fee rate printed on a fee notice, e.g. 2.0
    sender_email: str | None
    evidence: dict[str, SourceRef]   # field name → where it was read ("total", "bank_account", ...)

class ContractData(BaseModel):
    counterparty: str
    supplier_id: str | None
    kind: Literal["supply", "lease", "saas", "rate_card", "other"]
    start: date | None
    end: date | None
    price_schedule: list[dict]       # {item_code, unit_price, currency} or {rent_monthly, from, escalation_pct}
    bank_account: str | None
    renewal: dict | None             # {auto_renews: bool, renewal_date, notice_days}
    evidence: dict[str, SourceRef]

class Expectation(BaseModel):
    id: str                          # "E-S03-price-PM-RB12", "E-S02-fee-rate"
    subject: str                     # supplier_id or "company"
    kind: Literal["unit_price", "fee_rate", "bank_account", "email_domain", "recurring_amount",
                  "approval_limit", "price_tolerance", "forecast_assumption", "contract_term",
                  "account_code"]
    key: str | None = None           # item code, account, assumption name
    value: str | float
    tolerance: float | None = None   # fraction, e.g. 0.01
    valid_from: date | None = None
    valid_to: date | None = None
    source: SourceRef                # where this expectation comes from (contract, COMPANY.md, decision)
    learned_from: str | None = None  # decision ID if it was learned

class Finding(BaseModel):
    control: str                     # "PRICE-001", "BANK-001", ...
    severity: Literal["hold", "approval", "info"]
    title: str                       # plain language: "Price 8.3% above contract"
    detail: str                      # "RMB 118/unit vs RMB 109 in contract §4.2 (+8.26%)"
    expected: str | float | None
    actual: str | float | None
    evidence: list[SourceRef]
    expectation_id: str | None = None

class CellChange(BaseModel):
    file: str
    sheet: str
    cell: str                        # "C5" or a range "C5:N5"
    old: str | float | None
    new: str | float | None
    sources: list[SourceRef]
    reason: str

class ChangeSet(BaseModel):
    id: str                          # "CS-0001"
    title: str                       # "Enter Dongguan Precision invoice DPE/INV/0388"
    reason: str                      # becomes the commit message body
    trigger: str                     # doc path or user request
    changes: list[CellChange]
    findings: list[Finding] = []
    status: Literal["proposed", "accepted", "rejected", "held"]
    created_by: str
    created_at: datetime
    decided_by: str | None = None
    commit: str | None = None

class Question(BaseModel):
    id: str                          # "Q-0001"
    changeset_id: str
    text: str                        # plain language, written by the LLM from the findings
    findings: list[Finding]
    options: list[Literal["reject", "approve_once", "approve_and_remember"]]
    blocked_options_reason: str | None = None   # e.g. "Bank changes need a call-back (COMPANY.md policy)"

class Decision(BaseModel):
    id: str                          # "D-0001"
    at: datetime
    by: str
    question_id: str
    changeset_id: str
    answer: Literal["reject", "approve_once", "approve_and_remember"]
    reason: str                      # the user's words
    memory_updates: list[Expectation] = []
    commit: str | None = None
```

## Pipeline details

### Indexer (`indexer.py`)

- Walk the workspace (skip `.trace/`, `ground_truth/`, lock files `~$*`). Classify `kind` by folder first (`docs/invoices` → invoice, `docs/contracts` → contract, `docs/bank` → bank_statement, `docs/emails` → email, `sheets` → sheet, `ledger` → ledger, `COMPANY.md` → memory).
- `status`: files tracked in workspace git → `tracked`; untracked → `new`. Use `git ls-files` / `git status --porcelain`.
- `supplier_id`: from the extracted data when available, else by filename/domain hints against supplier_master.
- `used_in`: built from `sources.json` (every `sources[].doc`) and the register's `source_file` column.

### Reader / OCR (`reader.py`)

- Use PyMuPDF. For each page: `page.get_text()`. If it returns fewer than ~30 characters, the page is a scan → render at 200 dpi to PNG → **vision LLM OCR** ("Transcribe all text exactly, keep table rows on one line, keep Chinese characters"). Use `settings.llm_model_vision`.
- `.eml` / `.txt`: parse with `email` stdlib (from, to, date, subject, body). `COMPANY.md`: read as text. xlsx/csv: not OCR'd, read by `sheets.py`.
- Cache: `.trace/extracted/<sha256>.json`. Same file hash → no LLM call.

### Extractor (`extractor.py`)

- `llm.extract(page_texts, InvoiceData)` (or `ContractData`), with a system prompt that requires an exact `quote` and `page` for each key field.
- **Post-validation in code** (fail → re-ask once, then mark the field "needs review"):
  - `sum(line.amount) == subtotal`, `subtotal + tax == total` (±0.01).
  - `qty × unit_price == amount` per line.
  - Every `evidence.quote` actually appears in the page text (normalise whitespace).
- `supplier_id` is matched **in code**: name similarity against supplier_master (EN or ZH name) and invoice-number pattern. Never trust an LLM-produced ID.
- If extraction for the scanned Chinese invoice fails, the OCR text is still shown, and the user can fix fields in the UI before checks run.

### Expectations (`expectations.py`)

Seeded deterministically (`seed_brain.py`) from the workspace. LLM only for reading contract price clauses, validated against the PDF text:

| Kind | Seeded from | Example |
|---|---|---|
| `unit_price` | Contract price schedules (S03 property management agreement, schedule 1) | S03 PM-RB12 = HKD 8,800.00 |
| `fee_rate` | Side letter / LPA "rate of X% per annum" (S02 side letter §3.1) | S02 management fee = 1.50% |
| `price_tolerance` | COMPANY.md policies | 0.01 |
| `bank_account` | supplier_master + payments_history (last payments) | S01 = 6214 8320 0019 2049 |
| `email_domain` | supplier_master `email_domain` | S01 = prgfund.com |
| `approval_limit` | COMPANY.md ("Approves anything above HK$...") | HK$500,000 → V. Cheung (approver in `key`) |
| `account_code` | COMPANY.md conventions (per document kind) + register (per counterparty) | capital_call → 150, fee_notice → 455; S03 → 471 |
| `recurring_amount` | invoice_register + payments history | S05 USD 2,450; S04 rent learned from the lease decision |
| `forecast_assumption` | COMPANY.md (the line with "rent" and "assumed flat at HK$") | rent_monthly = 95,000 flat |
| `contract_term` | Contracts (end dates, renewal, notice) | S05 auto-renews 2026-11-16, 30-day notice |

### Checks (`checks.py`): deterministic controls

Each control is a plain function `(doc_data, expectations, register, history) -> list[Finding]`. IDs must match ground truth.

| ID | Fires when | Severity |
|---|---|---|
| `PRICE-001` | any line `unit_price > expected × (1 + tolerance)`, **or** a fee notice's `fee_rate_pct > expected fee_rate × (1 + tolerance)` | hold |
| `BANK-001` | invoice bank account ≠ expected bank account for the supplier | hold |
| `DOMAIN-001` | sender/contact email domain ≠ known domain (also catches lookalikes) | hold |
| `DUP-001` | same supplier + same invoice number after normalising (strip suffixes like `-R`, `/R`, ` (copy)`, spaces, case), or same supplier + same amount + invoice dates ≤ 7 days apart. **Not** a plain "same amount" rule: recurring invoices (art insurance USD 2,450, management fees) repeat the amount every month and must pass | hold |
| `UNKNOWN-001` | supplier not on supplier_master | hold |
| `AMOUNT-001` | recurring invoice amount differs from expected recurring amount by > tolerance | hold (ask) |
| `APPROVAL-001` | `amount_hkd > approval_limit` | approval (not a hold; "Needs V. Cheung approval") |
| `CONTRACT-001` | a new contract's terms differ from current expectations/forecast (e.g. new lease rent ≠ forecast rent) | info → triggers a proposed forecast update + question |

The emails folder is linked: a bank-change email from a domain that isn't the known domain adds evidence to BANK-001 and DOMAIN-001.

### Questions and decisions (`intake.py`, `decisions.py`)

- Any `hold` finding → a `Question`. The LLM writes the question text from the findings (plain language, one paragraph, cites evidence). The **options are set by code**:
  - `reject`: change set stays HELD (row written with `status=HELD` + reason), decision logged.
  - `approve_once`: entered this time only. Expectation unchanged. Reason logged.
  - `approve_and_remember`: entered, and expectations updated (e.g. new unit price valid from this invoice date, new recurring amount).
- **Policy guard:** for `BANK-001` and `DOMAIN-001`, `approve_and_remember` is blocked unless the reason mentions a call-back verification (COMPANY.md: "Email alone is never enough"). Show `blocked_options_reason`.
- Each decision is appended to `decisions.jsonl` and committed together with its change set: `"Decision D-0001: reject PRG2-DN-018 — bank change unverified (J. Yip)"`.

### Change sets and versioning (`changes.py`, `versioning.py`)

- `ChangeSet.apply()`:
  1. Write cells with openpyxl (`load_workbook(path)`, not `data_only`, so formulas survive). For appended register rows, write `amount_hkd` as a formula `=F{r}*G{r}` like the existing rows (check existing rows and copy their pattern).
  2. Add an Excel **cell comment** on each changed cell: `"Trace: <reason> — source: <doc> p.<page>"` (P1).
  3. Append one `sources.json` entry per changed cell (or per contiguous range).
  4. `git add -A && git commit` with subject = `ChangeSet.title`, body = reason + bullet list of sources + decision IDs, author = current user.
  5. Store the commit hash in the change set, `sources.json` entries and the decision.
- `history(file, sheet, cell)` = all `sources.json` entries covering that cell (range-aware), newest first, joined with `git show --format=%H|%an|%ad|%s` for each commit, plus the previous value from `git show <commit>^:<file>` read with openpyxl (P1 for old value).

### Ask the brain (`ask.py`)

- `llm.run_agent(question, tools=[...], system=...)` with tools:
  `search(query, k=8)`, `read_document(path, page=None)`, `read_sheet(file, sheet, range)`, `cell_history(file, sheet, cell)`, `list_decisions(subject=None)`, `get_expectations(subject=None)`, `list_files(kind=None, supplier_id=None)`, `contract_deadlines(within_days=30)` (computed in code).
- Final answer passed through `llm.extract` into `Answer {sentences: [{text, refs: [SourceRef]}]}`.
- **Citation validator:** drop or flag any sentence whose refs don't exist (doc path not in index, page out of range, quote not found, commit not in git, decision ID unknown). The UI shows refs as clickable chips.

### Search (`search.py`)

TF-IDF (scikit-learn, char n-grams 2–4 so Chinese works) over page texts from the index. Returns `(path, page, score, snippet)`. Rebuilt after each intake.

## LLM

- Through `app.llm.get_llm()` only. Labels on every call (`ocr`, `extract_invoice`, `extract_contract`, `question`, `ask`).
- **Wrapper change needed:** `app/llm/openrouter.py::_messages` currently flattens user content to text only. Add support for Converse-style image blocks: `{"image": {"format": "png", "source": {"bytes": b"..."}}}` → OpenAI `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`. Keep text-only messages unchanged. The fake provider should return a plausible OCR string for image prompts.
- Models (verify with `uv run python scripts/check_env.py` at kickoff, then pick by what passes):
  - `LLM_MODEL`: strong tool-caller for Ask and extraction (default `openai/gpt-oss-120b`).
  - `LLM_MODEL_FAST`: question wording, classification.
  - `LLM_MODEL_VISION` (new setting): a multimodal model for OCR. `gpt-oss` is text-only. Candidates to test: Qwen VL, Gemini Flash, GPT-4.1-mini / GPT-5-mini class models on OpenRouter. **Test the Chinese scanned invoice first** and pick the model on that test.
- Some providers restrict HK traffic. Confirm the chosen slugs answer from the venue network.

## Settings to add (`app/config.py`)

| Setting | Env | Default |
|---|---|---|
| `trace_workspace` | `TRACE_WORKSPACE` | `runtime/workspace` |
| `trace_seed_workspace` | `TRACE_SEED_WORKSPACE` | `workspace` |
| `llm_model_vision` | `LLM_MODEL_VISION` | (none; must be set for real OCR) |
| `trace_user` | `TRACE_USER` | `Jason Yip` (UI selector overrides; must be a person in COMPANY.md) |

Add them to `.env.example` with comments.

## Dependencies

Missing from `pyproject.toml` and needed: **`openpyxl`** (xlsx read/write) and **`pymupdf`** (PDF text + page render). Per repo rules the env owner adds them in a small PR: `uv add openpyxl pymupdf`. Everything else is already installed (pandas, scikit-learn, plotly, pydantic, streamlit). No GitPython (use subprocess). No tesseract.

## Company-specific data lives in the workspace

Changed when the demo moved to the family office: the app has no company constants. `app/data/company.py` reads COMPANY.md (name, people and emails, approval rule, email domain, forecast named range). Expectations for tolerance, approval, account codes per document kind and the rent assumption are parsed from COMPANY.md. The lease flow finds the forecast cells through the workbook's named range and splits them by year using the month headers. The Ask system prompt is built from the same data.
