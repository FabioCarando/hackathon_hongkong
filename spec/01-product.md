# 01 · Product

## The one-liner

**Trace is the finance team's brain.** It knows where every financial file is and where every number came from. It reads invoices and statements, fills in the team's spreadsheets, stops anything that doesn't match what it expects and asks why, and remembers every answer.

## Who it's for

- **User:** the fund accountant and accounts clerk at a Hong Kong single-family office (1–5 finance people). In the demo: Grace Lam (fund accountant) and Jason Yip (accounts clerk) at Lantau Peak Family Office.
- **Buyer:** the family office CFO, or the principal. In the demo: Raymond Ho (CFO); Victoria Cheung (principal, family member) approves large payments.
- **Beachhead:** HK single-family offices. Small teams handle capital calls, fund fee notices, property and household bills in Chinese and English, HKD/USD/RMB, with large amounts and real fraud risk (fake "new wire instructions" on capital calls).
- **Later:** multi-family offices, private banks and trust companies, and fund administrators.

## Today's workflow (what the team does by hand)

1. Collect documents: capital call and fee notices, invoices, bank and custodian statements, contracts, side letters, leases, emails.
2. Compare them against contracts and past history.
3. Run sanity checks for wrong or fraudulent entries.
4. Type the numbers into the spreadsheets the team manages itself.

## Pains

| Pain | What it looks like |
|---|---|
| **Manual entry** | Numbers from PDFs, some scanned, some in Chinese, typed into Excel one by one |
| **Scattered files** | "Where's the signed lease?" means searching email, drives and folders |
| **No history of why** | A spreadsheet shows *what* a number is, never why it changed or who decided. When someone leaves, the reasons leave with them |
| **Errors and fraud slip through** | Overcharges vs contract, duplicate invoices and fake "our bank account changed" emails get missed during routine entry |
| **Audit pain** | "Show me the support for this number" takes days to reconstruct |

## What Trace does: three pillars

### 1. Knows where everything is (file index and provenance)

- Indexes every file in the finance workspace: what it is, which counterparty it belongs to, when it arrived, and what was taken from it.
- Every spreadsheet has a full version history. Every important change carries a comment with what changed, why, who approved it and which document it came from.
- Click any cell → see where the number came from and every change it went through.

### 2. Reads documents and fills the sheets (intake)

- OCR that works on scanned and digital PDFs, in English and Chinese.
- Pulls out the useful fields: counterparty, document type (capital call, fee notice, invoice), number, dates, line items, amounts, fee rate, currency, bank account, sender.
- Proposes the new rows and cells in the team's CSVs and Excel files, each linked to the page and quote it came from.

### 3. Knows what to expect and asks when something doesn't fit (expectation memory)

- Keeps a memory of what is *expected*: contract prices, side-letter fee rates, counterparty bank accounts and email domains, usual amounts, recurring invoices, approval rules, forecast assumptions.
- When a document doesn't match, Trace **does not write it in**. It asks the user why.
  - **Not expected** → blocked. Wrong or fraudulent data stays out of the books.
  - **Expected** → the user's answer is saved as a **decision** with its reason. The memory updates so the same case passes next time. Company policy still applies, so for example a bank account change still needs a call-back, not just an email.
- The decision log becomes the team's memory: every exception, who decided it, and why.

Plus **"Ask the brain"**: questions in plain language ("Why is 2027 rental income 98,800?", "How much do we still owe Harbourview?", "Which contracts need action this month?"). Answers cite the documents, commits and decisions behind them.

## The loop that matters

```
document arrives → read (OCR) → extract fields → compare with what's expected
   ├─ matches     → propose rows/cells → human approves → saved + version commit with sources
   └─ doesn't fit → ask "why?" → reject (blocked, logged)
                               or approve (decision saved, memory updated) → saved + commit
later: anyone asks "why is this number like this?" → answer with sources and decisions
```

## Scope

| In this build | Next step (roadmap only) |
|---|---|
| File index, OCR, extraction, spreadsheet updates with approval | **Financial reports** (cash flow, P&L, budget vs actual), built on the brain |
| Version history with reasons and per-cell sources | Live mailbox / drive connectors |
| Expectation memory, checks, questions, decision log | Multi-user roles and approval chains |
| Ask the brain (cited answers) | Accounting-firm multi-client workspaces |
| Bank reconciliation, duplicate and fraud checks, contract deadlines (see `04`) | Payment execution |

## Other pain points the same brain solves

These reuse the same three pieces (index, sources, expectations). Priority is set in `04-features.md`.

| Pain | How the brain helps |
|---|---|
| Duplicate invoices / paying twice | Same document number, or same counterparty + amount + close date → blocked |
| Fund fee overcharges | Fee rate on the notice vs the side-letter rate ("2.00% charged, side letter says 1.50%") → blocked |
| Fake "bank details changed" emails | Bank account on the invoice ≠ the one on file, or the sender's domain is a lookalike → stop and ask |
| Bank reconciliation | Matches bank statement lines to invoices and payments; flags money with no document |
| Audit prep | Every cell already links to its source, so the support pack is one click |
| Key person leaves / onboarding | Decisions and reasons are stored; a new hire can ask the brain |
| Contract deadlines | Reads contracts; warns about renewals and notice periods ("Art insurance auto-renews; cancel by 17 Oct") |
| Approval rules | Payments over HK$500,000 are flagged for the principal's approval |
| Bilingual, multi-currency paperwork | Chinese/English OCR; HKD/RMB/USD with the month's FX rate recorded |

## Value in plain terms

- **Trust:** every number traces back to a document and a decision.
- **Safety:** nothing unexpected enters the books without a human saying yes.
- **Memory:** the reasons behind decisions stay when people leave.
- **Time:** no more retyping invoices or hunting for files.

## Name

"Trace" is the working name. The category line for the pitch: **"the finance team's brain"**. The old framing "Claude Code for finance" still works as the analogy: agent, diff, approve, commit, blame.
