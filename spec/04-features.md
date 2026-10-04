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

- Catalog of all workspace files with kind, supplier, title, status (new / tracked / processed / held), pages, OCR method, last commit.
- Filter by kind and supplier. Search box (F9).
- Click a file → preview (PDF page image or text), extracted fields, and **"Used in"**: every cell/row that cites it.
- ✅ Accept: the 5 inbox invoices, the 2027 lease and the 2 new emails show as **new**. Every other file shows as tracked. `docs/contracts/S01_supply_agreement_2026.pdf` lists the register/master cells that cite it (from `sources.json`).

## F3 · Reading documents (OCR): **P0**

- Digital PDFs via the text layer. Scanned PDFs (`scan_1002.pdf`, `scan_0930_2.pdf`) via the vision model. `.eml` via the email parser.
- Results cached by hash. Second run = no LLM call.
- ✅ Accept: the OCR text of `scan_1002.pdf` contains `SP-2026-0917`, `118`, `7731`, `306,500` and Chinese characters. `scan_0930_2.pdf` contains `INV-2318` and `33,900`.

## F4 · Extraction with evidence: **P0**

- Invoice → `InvoiceData` with a page + quote for invoice_no, date, total, currency, bank_account, sender_email and each line.
- Arithmetic checked in code. Quotes verified against the page text. Supplier matched in code.
- Fields can be corrected in the UI before checks run (P1; P0 = read-only display).
- ✅ Accept: for all 5 inbox invoices, the extracted fields match `expected.json › tasks[1].rows` (supplier_id, invoice_no, date, currency, amount, due_date). **Field accuracy ≥ 95%.**

## F5 · Expectation memory: **P0**

- Seeded from contracts, supplier master, payments history, register and COMPANY.md (`seed_brain.py`, also run on reset).
- "Memory" page lists expectations grouped by supplier, each with its source (clickable) and, if learned, the decision that created it.
- ✅ Accept: contains S01 SP-4410 unit price RMB 109 (source: S01 contract §4.2), S01 bank …2049, S01 domain shenzhenparts.com, 1% tolerance, HK$50k approval limit, rent 2027 = 80,000 assumption, S05 renewal 2026-11-16 with 30-day notice.

## F6 · Checks: **P0** (PRICE, BANK, DUP, APPROVAL) · **P1** (DOMAIN, UNKNOWN, AMOUNT, CONTRACT)

- Deterministic controls from `03`. Each finding has a plain-language title, the detail with numbers, and evidence chips (doc + page + quote).
- ✅ Accept: exactly the planted problems fire. `scan_1002.pdf` → PRICE-001 + BANK-001 (+ DOMAIN-001 at P1). `Invoice (3).pdf` → DUP-001. The 3 clean invoices → **no hold**. DPE/INV/0388 and SP-2026-0917 → APPROVAL-001 flag.

## F7 · Ask the user why (questions + decisions): **P0**

- Every held change set shows a question card: what's unexpected, the evidence, and the options.
- Options: **Reject** / **Approve once** / **Approve and remember**. The reason text box is required.
- Policy guard: "Approve and remember" is disabled for bank/domain changes unless the reason mentions a call-back.
- Decisions go to `decisions.jsonl` and are committed. "Approve and remember" updates expectations (with `learned_from`).
- ✅ Accept: rejecting SP-2026-0917 writes a HELD row + decision D-000x + commit. Approving a changed price "and remember" makes the same price pass on a re-run without a question.

## F8 · Change sets, diff and version history: **P0**

- Each proposed change set shows as a diff: file, sheet, cell, old → new, source chip, reason. Accept / Reject per change set.
- Accept → write xlsx → append `sources.json` → git commit (author = current user, message = title + reason + sources + decision IDs).
- "History" page: commit timeline (seeded commits plus new ones). Pick a commit → its changed cells and sources.
- **Cell blame:** pick file + sheet + cell → every change to that cell with when, who, why and source.
- ✅ Accept: after entering the 3 clean invoices, `invoice_register.xlsx` rows 19+ match `tasks[1]` (Entered rows), each new cell has a `sources.json` entry with the commit hash, and `git log -1` shows the reason. After the lease flow, blame on `Forecast!C9` shows the 2027 lease p.3 clause 4 commit **and** the older `cbcb6ff` "rent flat" commit.

## F9 · Search: **P0**

- One search box (Files page + Ask tool) over all document text. Works for Chinese.
- ✅ Accept: "lease" finds both leases. "銀行" or "bank account changed" finds the 2 Oct email and the S01 invoice.

## F10 · New contract → update what depends on it (lease flow): **P0**

- When `S04_lease_2027_signed.pdf` is processed: extract rent terms → CONTRACT-001 sees rent 82,400 ≠ forecast assumption 80,000 → question "A new lease was signed 29 Sep: HK$82,400/month from Jan 2027, +3% yearly. Your forecast assumes HK$80,000 flat (D. Wong, Aug). Update the forecast?" → on approval, a change set:
  - `Forecast!C9:N9` = 82,400, `O9:Z9` = 84,872 (computed in code: 82,400 × 1.03).
  - Forecast `Assumptions` sheet rent row updated, with source.
  - `supplier_master` S04 `contract_file` → the new lease.
  - Expectations: S04 recurring rent 82,400 from 2027-01-01, rent assumption updated, learned_from = decision. COMPANY.md assumption line updated (P1).
- ✅ Accept: matches `expected.json › tasks[0]` (24 cells), one commit, sources point to lease p.3 clause 4.

## F11 · Ask the brain (cited answers): **P0** (basic) · **P1** (validator)

- Chat page. Answers are sentences with source chips (doc page / commit / decision). Click a chip → opens the doc page or commit.
- Must handle: "Why is 2027 rent 82,400?", "Where is the signed lease?", "Why was the Shenzhen Parts invoice held?", "Which contracts need action in the next 30 days?".
- ✅ Accept (P0): the rent answer contains the facts in `tasks[2]` and cites the lease and at least one commit. The deadlines answer names CloudDesk and 2026-10-17. (P1) Citation validator rejects refs that don't exist.

## F12 · Contract deadlines: **P1**

- Computed in code from contract expectations: renewal date − notice days. Banner on the Inbox page: "CloudDesk auto-renews 16 Nov. Cancel by 17 Oct or commit USD 17,400."
- ✅ Accept: matches `tasks[3]`. Nothing else falls in the 30-day window.

## F13 · Excel cell comments: **P1**

- Each changed cell gets a comment `Trace: <reason> — <doc> p.<page> (<commit short>)`. Someone opening the xlsx in Excel sees the provenance.

## F14 · Bank reconciliation: **P2**

- Read `statement_2026-09.pdf` lines → match against `payments_history.csv` and GL 090 lines by date, amount and reference. Unmatched items become questions ("HK$6,680 paid on 22 Sep has no invoice. What was it?").
- ✅ Accept: all September statement lines match. Opening/closing balances = 4,167,996.59 / 3,886,435.79.

## F15 · Audit support pack: **P2**

- Pick a cell → export a zip/PDF with the value, its history, the source pages (images with the quote highlighted) and the decisions.

## F16 · Learn-then-pass demo: **P2**

- A generated January 2027 rent invoice at HK$82,400 passes with no question, because the brain learned it from the lease decision. Needs a generator addition (`docs/invoices/demo_later/`).

## Roadmap only: **P3**

- **Financial reports** built on the brain: monthly cash flow (ground truth already in `tasks[5]`), P&L, budget vs actual. The next step after the brain.
- Mailbox / drive connectors, multi-user roles and approval chains, accounting-firm multi-client workspaces, payments.
