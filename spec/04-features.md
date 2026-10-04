# 04 · Features

## Priority labels

| Label | Deadline | Meaning |
|---|---|---|
| **P0** | ~17:00, 4 Oct | The demo in `06` works end to end |
| **P1** | 21:00, 4 Oct (submission) | Depth and polish that raise the score |
| **P2** | 5–7 Oct (only if we reach the Top 7) | Extra pains, benchmarks, exports |
| **P3** | Roadmap | Pitch only, not built |

Rule: **no P1 work until every P0 acceptance criterion passes.**

---

## F1 · Runtime workspace and reset: **P0**

- App reads and writes `runtime/workspace`, copied from `workspace/`. "Reset demo" in the sidebar restores it in under 5 s.
- ✅ Accept: after a full demo run and reset, `git --git-dir=runtime/workspace/.trace/git log` shows the original 10 commits and the inbox is untracked again. `workspace/` in the outer repo is unchanged (`git status` clean).

## F2 · File index ("Files"): **P0**

The brain knows every file.

- Catalog of all workspace files with kind, counterparty, title, status (new / tracked / processed / held), pages, OCR method, last commit.
- Filter by kind and counterparty. Search box (F9).
- Click a file → preview (PDF page image or text), extracted fields, and **"Used in"**: every cell/row that cites it.
- ✅ Accept: the 6 inbox documents, the 2027 lease and the 2 new emails show as **new**. Every other file shows as tracked. `docs/contracts/S01_subscription_agreement_2024.pdf` lists the master cell that cites it (from `sources.json`).

## F3 · Reading documents (OCR): **P0**

- Digital PDFs via the text layer. Scanned PDFs (`scan_1002.pdf`, `scan_0930_2.pdf`) via the vision model. `.eml` via the email parser.
- Results cached by hash. Second run = no LLM call.
- ✅ Accept: the OCR text of `scan_1002.pdf` contains `PRG2-DN-018`, `7731`, `3,500,000` and Chinese characters. `scan_0930_2.pdf` contains `INV-PM-2318` and `18,500`.

## F4 · Extraction with evidence: **P0**

- Payable document → `InvoiceData` with its `kind` (capital_call / fee_notice / invoice), `fee_rate_pct` when printed, and a page + quote for invoice_no, date, total, currency, bank_account, fee rate, sender_email and each line.
- Arithmetic checked in code. Quotes verified against the page text. Supplier matched in code.
- Fields can be corrected in the UI before checks run (P1; P0 = read-only display).
- ✅ Accept: for all 6 inbox documents, the extracted fields match `expected.json › tasks[1].rows` (supplier_id, invoice_no, date, currency, amount, due_date). **Field accuracy ≥ 95%.**

## F5 · Expectation memory: **P0**

- Seeded from contracts (price schedules, side-letter fee rates, renewal terms), the counterparty master, payments history, register and COMPANY.md (`seed_brain.py`, also run on reset).
- "Memory" page lists expectations grouped by counterparty, each with its source (clickable) and, if learned, the decision that created it.
- ✅ Accept: contains S02 management fee rate 1.50% (source: side letter p.1 §3.1), S03 PM-RB12 unit price HKD 8,800 (schedule 1), S01 bank …2049, S01 domain prgfund.com, 1% tolerance, HK$500k approval limit (V. Cheung), account 150 for capital calls and 455 for fee notices, rent 2027 = 95,000 assumption, S05 renewal 2026-11-16 with 30-day notice. All company-level items come from COMPANY.md.

## F6 · Checks: **P0** (PRICE, BANK, DUP, APPROVAL) · **P1** (DOMAIN, UNKNOWN, AMOUNT, CONTRACT)

- Deterministic controls from `03`. Each finding has a plain-language title, the detail with numbers, and evidence chips (doc + page + quote).
- PRICE-001 covers both unit prices vs a price schedule and **fee rates vs the contract / side-letter rate**.
- ✅ Accept: exactly the planted problems fire. `scan_1002.pdf` → BANK-001 + DOMAIN-001. `HCP3_Q4_2026_Management_Fee.pdf` → PRICE-001 (2.00% vs 1.50%). `Invoice (3).pdf` → DUP-001. The 3 clean documents → **no hold**. HCP3-CN-2026-04 and PRG2-DN-018 → APPROVAL-001 flag ("Needs V. Cheung approval").

## F7 · Ask the user why (questions + decisions): **P0**

- Every held change set shows a question card: what's unexpected, the evidence, and the options.
- Options: **Reject** / **Approve once** / **Approve and remember**. The reason text box is required.
- Policy guard: "Approve and remember" is disabled for bank/domain changes unless the reason mentions a call-back.
- Decisions go to `decisions.jsonl` and are committed. "Approve and remember" updates expectations (with `learned_from`).
- ✅ Accept: rejecting PRG2-DN-018 writes a HELD row + decision D-000x + commit. Approving a changed price or fee rate "and remember" makes the same value pass on a re-run without a question.

## F8 · Change sets, diff and version history: **P0**

- Each proposed change set shows as a diff: file, sheet, cell, old → new, source chip, reason. Accept / Reject per change set.
- Accept → write xlsx → append `sources.json` → git commit (author = current user, message = title + reason + sources + decision IDs).
- "History" page: commit timeline (seeded commits plus new ones). Pick a commit → its changed cells and sources.
- **Cell blame:** pick file + sheet + cell → every change to that cell with when, who, why and source.
- ✅ Accept: after entering the 3 clean documents, `invoice_register.xlsx` rows 11+ match `tasks[1]` (Entered rows), each new cell has a `sources.json` entry with the commit hash, and `git log -1` shows the reason. After the lease flow, blame on `Forecast!C5` shows the 2027 lease p.3 clause 4 commit **and** the older `17b9fd4` "rental income flat" commit.

## F9 · Search: **P0**

- One search box (Files page + Ask tool) over all document text. Works for Chinese.
- ✅ Accept: "lease" finds both leases. "銀行" or "bank account changed" finds the 2 Oct email and the S01 invoice.

## F10 · New contract → update what depends on it (lease flow): **P0**

- When `S04_lease_2027_signed.pdf` is processed: extract rent terms and the counterparty (the tenant) → CONTRACT-001 sees rent 98,800 ≠ forecast assumption 95,000 → question "New lease signed 29 Sep: HK$98,800/month from Jan 2027, +3% each January. Your forecast still assumes HK$95,000 flat. Update the forecast?" → on approval, a change set:
  - The cells of the named range `RENT_INCOME_FORECAST` (named in COMPANY.md), split by year from the month headers: `Forecast!C5:N5` = 98,800, `O5:Z5` = 101,764 (computed in code: 98,800 × 1.03).
  - Forecast `Assumptions` sheet rent row updated, with source.
  - `supplier_master` S04 `contract_file` → the new lease.
  - Expectations: S04 recurring rent 98,800 from 2027-01-01, rent assumption updated, learned_from = decision. COMPANY.md assumption line updated (P1).
- ✅ Accept: matches `expected.json › tasks[0]` (24 cells), one commit, sources point to lease p.3 clause 4.

## F11 · Ask the brain (cited answers): **P0** (basic) · **P1** (validator)

- Chat page. Answers are sentences with source chips (doc page / commit / decision). Click a chip → opens the doc page or commit.
- Must handle: "Why is 2027 rental income for Flat 12A 98,800?", "Where is the signed lease?", "Why was the Pearl River capital call held?", "Which contracts need action in the next 30 days?", "How much do we still owe Harbourview Capital Partners III?" (from `commitments.xlsx` + the pending call).
- ✅ Accept (P0): the rent answer contains the facts in `tasks[2]` and cites the lease and at least one commit. The deadlines answer names the art insurance policy (S05) and 2026-10-17. (P1) Citation validator rejects refs that don't exist.

## F12 · Contract deadlines: **P1**

- Computed in code from contract expectations: renewal date − notice days. Banner on the Inbox page: "Meridian Fine Art Insurance Ltd auto-renews 16 Nov. Cancel by 17 Oct 2026 or commit to USD 29,400 for another year."
- ✅ Accept: matches `tasks[3]`. Nothing else falls in the 30-day window.

## F13 · Excel cell comments: **P1**

- Each changed cell gets a comment `Trace: <reason> — <doc> p.<page> (<commit short>)`. Someone opening the xlsx in Excel sees the provenance.

## F14 · Bank reconciliation: **P2**

- Read `statement_2026-09.pdf` lines → match against `payments_history.csv` and GL 090 lines by date, amount and reference. Unmatched items become questions ("HK$6,680 paid on 22 Sep has no invoice. What was it?").
- ✅ Accept: all September statement lines match. Opening/closing balances = 20,469,784.50 / 23,571,822.50.

## F15 · Audit support pack: **P2**

- Pick a cell → export a zip/PDF with the value, its history, the source pages (images with the quote highlighted) and the decisions.

## F16 · Learn-then-pass demo: **P2**

- A generated January 2027 rent receipt at HK$98,800 passes with no question, because the brain learned it from the lease decision. Needs a generator addition (`docs/invoices/demo_later/`).

## Roadmap only: **P3**

- **Financial reports** built on the brain: monthly cash flow (ground truth already in `tasks[5]`), P&L, budget vs actual. The next step after the brain.
- Mailbox / drive connectors, multi-user roles and approval chains, accounting-firm multi-client workspaces, payments.
