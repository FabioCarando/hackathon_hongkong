# Elevator Pitch — Trace

> Working name. Replace it freely. Alternatives: Ledger Code, Second Brain for Finance, Tally.

**One line:** Claude Code for finance teams. An AI agent that works inside the company's finance workspace (documents, spreadsheets, ledger), does the work you ask in plain language, produces the financial reports (P&L, cash flow, budget vs actual), shows every change as a reviewable diff, and remembers what changed, when, and why.

## 30-second script

> "AI agents like Claude Code changed how developers work. You ask for a task, the agent reads the whole codebase, does the work, shows you a diff to approve, and git remembers every change and why. Finance teams got none of that. They still type numbers from PDFs into Excel, dig through folders for one figure, and ask colleagues 'why is this number like this?'
>
> Trace is that agent for finance. Ask it to 'enter this week's invoices' or 'update the forecast for the new lease'. It reads the documents, in English or Chinese, edits the spreadsheet, and shows you exactly which cells changed and where each number came from. You approve; it records why. A week later anyone can ask 'why did rent go up?' and get the answer with the source.
>
> An analyst's hour of work in a minute, with full history. The AI prepares, a human approves."

## Problem

- **Manual work:** invoices, statements and contracts are keyed into spreadsheets by hand. Charts and reports are rebuilt by hand every month. *(verify hours-per-week figure)*
- **Scattered knowledge:** the answer to "what's our rent next year?" sits in clause 4 of a PDF in someone's folder. Finding one figure means searching email, drives and spreadsheets.
- **No history of why:** spreadsheets show *what* a number is, never *why*. When the analyst who built the budget leaves, or the auditor asks "show me the support for this number", the team loses days reconstructing it.
- **Mistakes slip through while busy:** overcharges against contract prices, duplicate invoices and fake "our bank details changed" emails get missed because nobody cross-checks while doing routine entry.

## Buyers

| Segment | Pain | Who signs |
|---|---|---|
| HK SMEs (20–300 staff) with 1–5 finance people | Manual entry, scattered documents, key-person risk | Finance manager / financial controller, owner |
| HK trading and import companies with mainland suppliers | Bilingual paperwork, many suppliers, HKD/RMB/USD | Financial controller, CFO |
| Accounting and bookkeeping firms serving SMEs | Same routine work across dozens of client workspaces | Partner |
| Brokers, payment firms and other fintechs (iFX audience) | Their own back office: vendor contracts, liquidity provider and SaaS invoices, forecasts | CFO / Head of Finance |

**Beachhead:** HK trading companies importing from mainland China. Small finance teams, bilingual documents and lots of routine entry make the time savings obvious.

## Solution: how it works

1. **A finance workspace:** the company's documents, spreadsheets and ledger in one place, like a code repository. A company memory file holds the context: budget assumptions, policies, how accounts are named.
2. **Ask for a task in plain language:** "enter these invoices", "update the forecast for the new lease", "prepare September's cash flow report", "build a chart of Q3 costs by supplier", "prepare support for the revenue number". The agent plans, reads the documents, opens the spreadsheets, and every step is visible.
3. **Review the diff:** proposed changes show as a spreadsheet diff, old → new, with the source document and quote behind each cell. Accept or reject. Nothing changes without approval.
4. **Every change is remembered:** each accepted change is recorded with who, when, why and from which document, like a git commit. Anyone can click a cell and ask "why is this number like this?"
5. **It notices problems while working:** like Claude Code spotting a bug near the line it's fixing. While entering invoices it checks them against contracts and payment history: "This invoice is 8% above contract and the bank account changed. I've held it."

## Why now

- Agents that use tools and work through multi-step tasks became reliable in 2025–26. Developers already work this way every day.
- Multimodal models read messy scanned PDFs and mixed Chinese/English documents without template setup.
- Long context lets the agent hold a supplier's whole history (contract, past invoices, emails) in one step.
- The pattern that makes agents trustworthy for code (diffs, approval, history) maps directly onto the controls finance already requires.

## Differentiation

- **An agent, not a point tool:** invoice capture tools, contract tools and BI tools each do one job. Trace does whatever the finance team asks across all their files.
- **Diffs and history built in:** every change is reviewable before it happens and traceable after. The audit trail is a by-product of working, not extra work.
- **Memory of intent:** it keeps the *why*, not just the numbers.
- **Built for HK:** Chinese and English documents, HKD/RMB/USD, mainland supplier invoices.
- **Reports come out of the work:** P&L, cash flow and budget vs actual are built by Trace straight from the workspace, so every figure clicks back to its source document. No separate reporting system to set up.
- **Works with what they have:** reads and writes the Excel files and folders finance already uses.

## Business model

- SaaS per seat, plus usage tiers for document volume.
- Accounting-firm plan: one firm, many client workspaces.
- Land with routine entry and forecast updates (time saved in week one), expand into reporting and audit support.

## Ask (Final)

- 3–5 HK SMEs or accounting firms from the expo floor as pilot partners.
- Introductions to finance teams willing to share anonymised document sets.

## Closing line

> "Developers got an AI that does the work and remembers why. Now finance does too."

## Numbers to verify before going on stage

Judges will ask where the numbers come from. Use sourced figures, or a quote from a real finance professional.

- [ ] Hours per week finance teams spend on manual data entry and spreadsheet updates
- [ ] Cost of processing one invoice manually vs automated (Ardent Partners / APQC benchmarks)
- [ ] Hours a finance team spends on audit support requests per year (ideally a quote from a real controller)
- [ ] Business email compromise losses for the latest year (FBI IC3 report; HK Police figures on email scams)
- [ ] Developer productivity gains from AI coding agents (a published study, for the analogy)
