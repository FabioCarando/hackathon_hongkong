# Revised Direction — Trace

> Agreed after a team discussion on 2026-10-04. Data control and provenance now come first. Reports are built on top of that.

## Current workflow (what the finance team does today)

1. Collect financial documents: invoices, receipts, bank statements.
2. Compare them against contracts.
3. Run sanity checks to catch fraudulent or wrong entries.
4. Update the spreadsheets by hand. **We manage these sheets ourselves. No external ERP.**

## New priority

**Trace keeps full control of the data.** For every number in every sheet, Trace knows where it lives and which document it came from.

## Core pillars

### 1. Provenance and version history

- Every spreadsheet keeps a full history of its versions.
- Every important change gets a comment that says what changed, why, and which source document caused it.
- Trace keeps an index of every file the finance team works with, so any document can be found right away.

### 2. Document intake and structuring

- OCR that works reliably on PDFs (scanned and digital) and turns them into text.
- Pull out the useful fields: amounts, dates, counterparty, category (income, expense, etc.).
- Write those fields into the right CSVs and Excel sheets automatically.
- Every entry links back to its source file. This feeds pillar 1.

### 3. Expectation memory and anomaly questions

- Trace keeps a memory of what is "expected": contracts, recurring suppliers, usual amounts, payment schedules.
- When a new invoice doesn't match, Trace **does not add it straight away**. It asks the user why.
  - **Not expected** → the entry is blocked, so wrong or fraudulent data stays out of the sheets.
  - **Expected** → the user's answer is saved as a decision. The memory updates, and similar cases later pass without asking.
- Result: a running log of finance decisions and the reasons behind them.

## End-to-end flow

```
New document → OCR → extract fields → check against expectation memory
   ├─ match    → write to sheet + versioned change comment + link to source
   └─ mismatch → ask user → reject  OR  approve + save decision to memory → write
```

## Value in plain terms

- **Trust:** every figure can be traced back to its source document.
- **Fraud safety:** nothing unexpected enters the books without a human saying yes.
- **Institutional memory:** the reasons behind decisions don't leave when people do.
- **Less manual work:** no more retyping invoices into spreadsheets.

## Open questions

- Where is the "expectation" first set: from contracts alone, from past history, or entered by hand?
- Who can approve a mismatch? Any team member, or only certain roles?
- Version history: git-style snapshots of each file, or a log at the cell level?
- Does the existing P0 task (monthly cash flow report) stay as the demo, built on top of this? Or does provenance become the demo?
