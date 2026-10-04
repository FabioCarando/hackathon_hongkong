# Prompt: generate the fake finance workspace

> Paste everything below the line into a coding agent (Claude Code etc.) at the repo root.
> Design goal: **realistic structure, cheap text.** The agent writes ONE deterministic Python generator.
> All volume (rows, PDFs, scans, git history) comes from code + templates, not from the LLM writing prose.

---

## Task

Write `scripts/generate_workspace.py`: a single, deterministic (fixed seed), re-runnable script that builds a fake finance workspace in `workspace/` for **Trace**, a "Claude Code for finance" agent. Read `ideas/trace/01-elevator-pitch.md` and `ideas/trace/02-implementation.md` first for context (demo script, tools, controls).

**Token budget rule:** do not write long prose. Every document gets a realistic *layout and fields*, plus at most 2–3 short sentences of real text. Contract boilerplate = a list of ~8 one-line generic clauses reused across contracts. Only the clauses the demo depends on (listed below) are written specifically. Use Faker (seeded) for volume rows. Keep all company/supplier data in compact Python dicts at the top of the script; every document and sheet is rendered from those dicts, so numbers are consistent everywhere.

Dependencies: openpyxl, fpdf2 (PDFs with a CJK font, e.g. Noto Sans CJK TC from `fc-list`), pymupdf + Pillow (for "scanned" versions). If missing, list them for the env owner instead of editing `pyproject.toml`. Add `workspace/` to `.gitignore` (it has its own git repo).

## The company

- **Harbour Lane Trading Ltd (海港貿易有限公司)**, Hong Kong, 18 staff. Imports electronic components from Shenzhen/Dongguan, resells to HK and SE Asia customers.
- Functional currency HKD. Also deals in RMB and USD. FY = calendar year.
- "Today" = **2026-10-05**. The September close is in progress. The finance team is Anna Chan (finance manager) and Ken Lau (accounts clerk). The owner/director is David Wong.
- Fixed FX for the demo (`fx_rates` sheet, monthly): USD 7.80 and RMB 1.08 HKD, with small month-to-month variation.
- All bank names, addresses and registration numbers must be clearly fictional (no real banks or companies).

## Suppliers (5) and what each one is for

| ID | Supplier | Location / currency / language | Role in demo |
|---|---|---|---|
| S01 | Shenzhen Parts Co., Ltd. 深圳市零件有限公司 | Shenzhen, RMB, invoices **in Chinese** | **Planted problem:** this week's invoice has a unit price 8.3% above contract (contract §4.2: RMB 109/unit, invoice RMB 118). It also has a **changed bank account** (…7731 vs …2049 on the last 6 payments) and arrives from a **lookalike domain** (`shenzhen-parts.co` vs real `shenzhenparts.com`). |
| S02 | Dongguan Precision Electronics 东莞精密电子有限公司 | Dongguan, USD, **bilingual** EN/中文 | Clean supplier (to measure false holds) |
| S03 | Pacific Freight Logistics Ltd | HK, HKD, English | **Planted problem:** a **duplicate invoice**: INV-2291 entered on 3 Sep, re-sent as "INV-2291-R" with the same amount, dated 26 Sep |
| S04 | Kowloon Bay Properties Ltd | HK, HKD, landlord | **New warehouse lease** for 2027 (demo task 1) |
| S05 | CloudDesk Inc. | US, USD, SaaS | Contract **auto-renews 2026-11-16** for 12 months; 30-day notice → cancellation deadline **2026-10-17**. Shows the deadline-tracker angle |

## Folder structure to generate

```
workspace/
  COMPANY.md                      # company memory (see below)
  docs/
    contracts/
      S01_supply_agreement_2026.pdf     # bilingual; §4.2 price schedule (3–4 items incl. RMB 109/unit); payment 60 days; bank acct …2049
      S02_supply_agreement_2026.pdf
      S03_freight_rate_card_2026.pdf    # 1 page, rate table
      S04_lease_2027_signed.pdf         # 3 pages; p.3 clause 4: rent HK$82,400/month from 1 Jan 2027, +3% every 1 Jan; signature block
      S04_lease_2024_2026.pdf           # old lease: HK$80,000/month flat, expires 31 Dec 2026
      S05_clouddesk_order_form.pdf      # USD 1,450/month; auto-renewal + 30-day notice clause
    invoices/
      2026-07/ 2026-08/ 2026-09/        # ~15 historical invoices across suppliers, already entered in the register
      inbox/                            # 5 NEW invoices for "enter this week's invoices":
                                        #   S01 (Chinese, planted price+bank problem)
                                        #   S02 (bilingual, clean)
                                        #   S03 INV-2291-R (duplicate)
                                        #   S03 normal new freight invoice (clean)
                                        #   S05 monthly SaaS (clean, USD)
    bank/
      statement_2026-09.pdf             # fictional "Victoria Harbour Bank"; opening/closing balances must reconcile with the transaction lines
    emails/                             # .eml or .txt, 3–6 lines each
      2026-09-29_landlord_lease_signed.eml
      2026-10-02_shenzhenparts_bank_change.eml   # from accounts@shenzhen-parts.co: "our bank account changed, please pay new account"
      2026-08-14_david_forecast_assumptions.eml  # "keep rent flat in 2027 until lease is renewed"
  sheets/
    invoice_register.xlsx     # AP register Jul–Sep: date, supplier_id, supplier, invoice_no, currency, amount, fx_rate, amount_hkd (formula), account_code, due_date, status, source_file
    supplier_master.xlsx      # id, name_en, name_zh, email_domain, bank_name, bank_account, currency, payment_terms, contract_file
    forecast_2027_2028.xlsx   # monthly P&L forecast, 24 months; "Rent" row = HK$80,000 flat (named range RENT_FORECAST); revenue, COGS, salaries, freight, software, utilities
    budget_vs_actual_2026.xlsx # Jan–Sep actual vs budget by account, variance + % columns (formulas); Facilities and Freight noticeably over budget
    fx_rates.xlsx
  ledger/
    chart_of_accounts.csv     # ~25 accounts, standard codes (200 Sales, 310 COGS, 469 Rent, 425 Freight, 485 Software, ...)
    gl_export_2026.csv        # Jan–Sep journal lines (~400–600 rows), standard GL columns; debits = credits per journal; totals agree with budget_vs_actual actuals
    payments_history.csv      # past payments: date, supplier_id, amount, currency, bank_account_paid → S01's last 6 all to …2049
  ground_truth/
    expected.json             # see below
```

### Realism checklist (cheap, but it's what makes it look real)
- Invoice numbering differs per supplier (`SP-2026-0917`, `DPE/INV/0388`, `INV-2291`, `CD-10044`). Filenames are inconsistent too (`scan_0926.pdf`, `INV-SP-2026-0917.pdf`, `Invoice (3).pdf`).
- **2 inbox invoices are "scanned":** render to image, grayscale, rotate 0.5–1.5°, add light noise/blur, save as image-only PDF. One of them is the Chinese S01 invoice.
- Line items × qty = line totals; subtotal + tax = total. HK suppliers have no tax. Mainland export invoices show 0% tax.
- No invoice dates on weekends. Due dates follow the payment terms. Amounts in the register match the PDFs exactly.
- Each supplier gets a consistent letterhead layout (name, address, BR/registration no., bank block), each one different from the others.
- The lease has a signature block, page numbers and clause numbering, so "p.3, clause 4" is a real location.
- The bank statement shows the September payments that appear in `payments_history.csv`.

## COMPANY.md (short, ~40 lines)
Company profile; people and roles; account naming conventions; supplier list with known domains; policies: **price tolerance 1% vs contract**, approval needed above HK$50k, payments only to bank accounts on the supplier master; forecast assumptions, including **"Rent assumed flat at HK$80,000 in 2027 pending lease renewal (D. Wong, Aug 2026)"**.

## Git history (inside `workspace/`)
`git init` and create ~8 backdated commits (set GIT_AUTHOR_DATE/GIT_COMMITTER_DATE; authors Anna/Ken), each building the workspace in stages: "Budget 2026 approved", "Enter July invoices", "Enter August invoices", "Forecast 2027–28 v1: rent flat pending lease renewal", "Enter early September invoices (incl. Pacific Freight INV-2291)". Add a sidecar `.trace/sources.json` that maps a few historical cells to their source doc + page + quote, using the same schema the app will use: `{file, sheet, cell, value, sources:[{doc, page, quote}], reason, commit}`. The inbox invoices and the new lease stay **uncommitted** (they're the demo).

## ground_truth/expected.json
Used for evaluation (`03-evaluation.md`). Include:
- `planted_problems`: each with id, invoice file, control that should fire (PRICE-001, BANK-001, DOMAIN-001, DUP-001), and the evidence values.
- `clean_invoices`: files that must NOT be held.
- `tasks`: 5 tasks with the expected end state:
  1. "Update the forecast for the new lease" → 24 RENT_FORECAST cells: 2027 = 82,400; 2028 = 84,872; source = lease p.3 clause 4.
  2. "Enter this week's invoices" → expected register rows for the 3 clean invoices (all fields) + 2 held.
  3. "Why is 2027 rent 82,400?" → expected answer facts + sources.
  4. "Which contracts need action in the next 30 days?" → CloudDesk, notice by 2026-10-17.
  5. "Why is Facilities over budget YTD?" → expected drivers from the GL.

## Verification (run before finishing)
- The script runs twice and produces identical output (apart from git hashes).
- Assertions inside the script: register totals = PDF totals; GL balances; bank statement reconciles; S01's history is all on …2049.
- Render the S01 inbox invoice, the lease p.3 and one scanned invoice to PNG and look at them yourself to confirm they're readable and look plausible.
- Print a short tree + row counts summary.
