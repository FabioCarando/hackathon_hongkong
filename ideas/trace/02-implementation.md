# Practical Implementation

Guiding principle: **copy what makes coding agents trustworthy.** The agent reads freely, but every write is a proposed diff that a human accepts. Every accepted change becomes a commit with a reason and sources. Checks that guard money (price vs contract, bank details, duplicates) are deterministic code the agent must run, not LLM judgement.

## Urgency labels

| Label | Deadline | Meaning |
|---|---|---|
| **P0** | ~17:00, 4 Oct | Core demo flow works end to end |
| **P1** | 21:00, 4 Oct (submission) | Polish and depth that raise the score |
| **P2** | 5–7 Oct (only if we reach the Top 7) | Benchmarks, extra tools, deck |
| **P3** | Roadmap | Mentioned in the pitch only, not built |

> ⚠️ Team has little frontend experience. One web screen with three panels (chat · spreadsheet/diff · document), built on the existing Streamlit boilerplate. Polish beats breadth.

## Claude Code → Trace mapping

| Claude Code | Trace | How we build it |
|---|---|---|
| Repository | **Finance workspace** | A folder: `docs/` (PDFs, images), `sheets/` (xlsx), `ledger/` (CSV exports) |
| CLAUDE.md | **COMPANY.md** | Company memory: assumptions, policies, account names, known suppliers. The agent reads it every task and proposes updates |
| Tools (read, edit, bash) | **Finance tools** | Read document, read sheet, propose cell edits, search, history, run checks, make chart |
| Diff + accept/reject | **Spreadsheet diff** | Changed cells old → new, each with source doc + quote; accept / reject per change set |
| Git commit + message | **Change log** | A real git repo under the workspace; commit message = why; sidecar JSON = per-cell sources |
| `git blame` | **"Why is this number like this?"** | Look up the commits that touched a cell, answer with sources |
| Hooks | **Controls** | Checks that always run on certain actions (e.g. any invoice entry), whatever the agent decides |
| Permission prompts | **Approval** | Reads are free; every write needs approval |

## Architecture

```
 user ──► chat panel
            │
            ▼
   ┌──────────────── AGENT LOOP (LLM via OpenRouter, tool calling) ────────────────┐
   │  reads COMPANY.md · plans · calls tools · streams each step to the UI          │
   └───────┬──────────────┬───────────────┬───────────────┬───────────────┬────────┘
           ▼              ▼               ▼               ▼               ▼
     read_document   read_sheet     propose_edits    history / why    make_chart
     (vision LLM,    (openpyxl /    (staged, NOT     (git log +
      EN + 中文)      pandas)        applied)         cell sources)
                                         │
                                         ▼
                              CONTROLS (deterministic hooks)
                              price vs contract · bank details changed
                              sender domain · duplicate invoice
                                         │
                                         ▼
                              DIFF VIEW ──► human accepts / rejects
                                         │
                                         ▼
                              apply to xlsx ─► git commit (why + sources)
```

## Stack

| Need | Choice |
|---|---|
| LLM reasoning + tool calling | **OpenRouter** with our own API keys; OpenAI-compatible API, so the model can be swapped by config |
| Document reading (PDF/scans, EN + 中文) | A multimodal model on OpenRouter; PDF pages rendered to images with PyMuPDF |
| Spreadsheet read/write | openpyxl (keeps formatting, comments) + pandas for analysis |
| Formula recalculation | LibreOffice headless, or keep demo sheets mostly values with few formulas |
| Change history | git (via GitPython) on the workspace folder + sidecar JSON for per-cell sources |
| Charts | Plotly (shown in UI, exportable as PNG into reports) |
| Frontend | Streamlit (existing boilerplate): `st.chat_message`, styled dataframes for diffs, page images for documents |
| Storage | Local filesystem; nothing else needed for the demo |

Notes:
- **Pick models at kickoff:** one strong tool-calling model for the agent loop, one good vision model for documents (can be the same). Test Chinese invoice reading first.
- Some providers restrict access from HK. Confirm the chosen models actually respond through OpenRouter from the venue network.
- Keep a cheap fast model as fallback if the main one is slow on stage.

---

## 1. Workspace and memory

| Component | Label |
|---|---|
| Fake company workspace: HK trading company, ~5 suppliers (2 mainland, Chinese invoices), contracts, a lease, ~20 invoices, payment history CSV, forecast xlsx, budget xlsx, a few email threads as PDFs/text | **P0** |
| COMPANY.md with assumptions ("rent assumed flat in 2027 pending lease renewal", supplier list, account names) | **P0** |
| Planted problems: invoice above contract price, changed bank account + lookalike sender domain, a duplicate invoice | **P0** |
| Agent proposes updates to COMPANY.md when it learns something ("lease renewed at +3%/yr") | P1 |
| Workspace initialised as a git repo with a believable history of past commits | P1 |

Our business teammate owns the fake workspace. A believable dataset is half the demo.

## 2. Agent and tools

The agent is a standard tool-calling loop: model gets the task, COMPANY.md and the tool list; it calls tools until done; the UI streams every step ("Reading lease_2027.pdf page 3…").

| Tool | What it does | Label |
|---|---|---|
| `list_files` / `search` | Find documents and sheets; keyword search over extracted text | **P0** |
| `read_document` | PDF/image → text + structured fields, each field with page + quote | **P0** |
| `read_sheet` | Sheet → table with cell references | **P0** |
| `propose_edits` | Stage cell changes `{sheet, cell, old, new, sources[], reason}`; never writes directly | **P0** |
| `history` | Commits that touched a cell or file, with messages and sources (the "blame" tool) | **P0** |
| `run_checks` | Runs the controls on an invoice; also triggered automatically as a hook | **P0** |
| `build_report` | Builds a financial report (first: monthly cash flow) from the ledger; totals computed in code, every line traced to its GL rows | **P0** |
| `make_chart` | Builds a Plotly chart from a sheet range; saves it into the workspace | P1 |
| `ask_user` | Ask one question mid-task ("No reason found for this change. Why?") | P1 |
| `write_memory` | Propose an edit to COMPANY.md (also goes through the diff) | P1 |
| `export_pack` | Audit support pack: number → sources → commits, as a PDF/zip | P2 |
| Skills (saved procedures like "month-end accruals") | | P3 |

### Controls (hooks)

The **LLM never decides whether money is at risk.** Controls are plain code that runs every time the agent proposes an invoice entry. Their result is shown in the diff and the agent explains it.

| Control | Example output | Label |
|---|---|---|
| Unit price above contract price | "HK$118/unit vs HK$109 in contract §4.2 (+8.3%)." | **P0** |
| Bank details differ from previous payments to this supplier | "Account ends 7731; last 6 payments went to ...2049." | **P0** |
| Sender domain doesn't match supplier's known domain | "shenzhen-parts.co vs shenzhenparts.com." | P1 |
| Duplicate invoice (same number, or same supplier + amount + close date) | "Matches INV-2291 entered on 3 Sep." | P1 |

Example control:

```yaml
id: PRICE-001
runs_on: propose_edits where target = invoice_register
indicator: "Invoice unit price above the contracted unit price"
condition: invoice.line.unit_price > contract.price_for(line.item) * (1 + tolerance)
tolerance: 0.01
on_fail: hold_entry   # entry staged as "held", needs explicit approval
evidence: [invoice.line.source, contract.price_clause.source]
```

## 3. Diff, approval and history

This is the part that makes it feel like Claude Code. It must look good.

| Component | Label |
|---|---|
| Chat panel streaming agent steps (tool calls visible, collapsible) | **P0** |
| Diff view: changed cells highlighted, old → new, source + quote on each row | **P0** |
| Accept / reject per change set; held entries marked red with the control's reason | **P0** |
| On accept: write xlsx, git commit with reason + sources | **P0** |
| Document panel: source page image with the quoted text highlighted | P1 (P0: show page image + quote text) |
| Click a cell → "why?" answer from history, every claim linked to a commit or document | P1 |
| Validator: rejects any answer sentence without a valid source reference | P1 |
| Download the updated xlsx with a cell comment per changed value ("source: lease_2027.pdf p.3") | P2 |
| Multi-user permissions, roles, approval chains | P3 |
| Live mailbox connector | P3 |

## 4. Financial reports

Trace produces the reports itself; there is no separate accounting or reporting system. Same rule as the controls: **the LLM picks and explains, code does the arithmetic.**

| Component | Label |
|---|---|
| **Monthly cash flow report** ("Prepare September's cash flow report"): opening cash → receipts and payments grouped by category (customers, suppliers, rent and facilities, payroll, freight, software, other) → closing cash. Built from the bank account lines (090) in `ledger/gl_export_2026.csv` | **P0** |
| Reconciles to `docs/bank/statement_2026-09.pdf`: opening and closing balance must match the statement, or the report says by how much and why | **P0** |
| Saved as a new sheet (`sheets/cash_flow_2026-09.xlsx`) through the normal diff → accept → commit flow; each line cites its GL rows and bank statement lines | **P0** |
| Short commentary from the agent ("Half of September's HK$1.26m outflow was two supplier TTs, to Shenzhen Parts and Dongguan Precision; payroll was the biggest single item"), every figure from the report, none typed by the LLM | P1 |
| Cash flow chart (bar of inflows/outflows by category) via `make_chart` | P1 |
| P&L and budget vs actual for a chosen month | P2 |
| Balance sheet, cash flow forecast from the forecast sheet | P3 |

---

## Demo script (3 min + 2 min Q&A)

Fake company: **a HK trading company importing electronic parts from Shenzhen.**

1. **(0:00)** "Claude Code changed how developers work. Finance teams never got that." One painful number.
2. **(0:20)** Type: *"We signed the new warehouse lease. Update the forecast."* → steps stream: reads the lease PDF, finds the 3% escalation clause, opens the forecast → **diff appears**: 12 rent cells, old → new, each citing "lease p.3, clause 4". Accept → committed. ← first wow
3. **(1:10)** Type: *"Enter this week's supplier invoices."* → reads 5 PDFs, one in Chinese → proposes entries. One row is red: **"8% above contract and the bank account changed. I've held it."** ← second wow
4. **(1:45)** Type: *"Prepare September's cash flow report."* → cash flow sheet appears in the diff, opening and closing cash matching the bank statement, each line clickable to its ledger rows. Accept → committed.
5. **(2:10)** Switch user. Click the rent cell: *"Why did rent go up?"* → "Changed on 4 Oct by Anna, from lease_2027.pdf clause 4 (+3%/yr). Previously flat per COMPANY.md assumption." Every part clickable.
6. **(2:35)** Metrics slide (from `03-evaluation.md`), business model, ask.

## Timeline on 4 Oct

| Time | Goal |
|---|---|
| 09:30–10:30 | Kickoff, confirm rules and criteria, freeze scope, pick OpenRouter models + Chinese reading test |
| 10:30–14:00 | In parallel: fake workspace (business teammate) · agent loop + tools · diff/commit engine · Streamlit layout |
| 14:00–17:00 | Wire it together; **demo steps 2, 3 and 4 working end to end by 17:00** |
| 17:00–19:00 | P1 items ("why?" from history, document highlights, charts), UI polish, **record the backup video** |
| 19:00–21:00 | Pitch rehearsal ×3, submission |

## Risks

| Risk | Mitigation |
|---|---|
| Model unreliable at tool calling / slow on stage | Test 2–3 models at kickoff; cap steps per task; pre-warm; cache the demo run as fallback |
| Chinese document reading is poor | Test first; use clean scans for the demo invoice; pick the model on this test |
| Model provider blocked from HK through OpenRouter | Verify at kickoff from the venue network; have a second provider configured |
| xlsx formulas don't recalculate after openpyxl writes | Keep demo sheets mostly values; recalc with LibreOffice headless if needed |
| Agent edits the wrong cells | Diff review is the safety net; constrain `propose_edits` to named ranges in the demo |
| Diff view looks clunky in Streamlit | Spend real time on it: it's the hero screen. Colour-coded dataframe, one row per change |
| Venue wifi fails | Backup video; cached results so the UI still runs offline |
| Scope creep | Anything not P0 waits until demo steps 2, 3 and 4 work |
