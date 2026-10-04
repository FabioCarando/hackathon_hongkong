# 07 · Pitch and competition fit

## Event

**iFX Hack Hong Kong 2026** (iFX + HKU Business School, powered by AWS). Theme: **"Build the Future of Finance with AI"**. Qualifier Sun 4 Oct, 09:30–21:00, HKU. **Top 7** present at iFX EXPO Asia, HKCEC, Thu 8 Oct, with 5–7 Oct to keep building. Prizes HKD 16k / 8k / 4k. Full sources: `ideas/COMPETITION_CRITERIA.md`.

Judging (assumed from the Cyprus edition): **Innovation · Technical execution · Functionality · Problem-solving approach · Industry impact.** The jury and audience are trading/fintech industry people who judge as buyers.

## 30-second script

> "Every family office finance team has the same three problems. They retype capital calls, fee notices and invoices from PDFs into Excel. They hunt through folders for the one signed side letter. And nobody remembers *why* a number changed, until the auditor asks or someone leaves.
>
> Trace is the finance team's brain. It knows every file and where every number came from. It reads capital calls, fee notices and invoices, even scanned ones in Chinese, and fills in the team's own spreadsheets. When something doesn't fit what it expects, like a fee above the side-letter rate or a fund's bank account suddenly changing, it doesn't write it in. It asks why, and it remembers the answer.
>
> Every number has a source, every change has a reason, and nothing unexpected enters the books without a human saying yes."

**Closing line:** "Your finance team's memory shouldn't walk out the door at 6pm."

## Problem → solution in one table

| Pain | Trace |
|---|---|
| Manual entry from PDFs, Chinese and English | OCR + extraction, proposed as a diff, one click to accept |
| Files scattered everywhere | One index of every file, searchable, linked to the numbers it supports |
| No history of why | Version history with a reason and source on every change; cell blame |
| Overcharges, duplicates, bank-change fraud | Checks against what's expected; stop and ask; policy guard |
| Knowledge leaves with people | Decision log + "Ask the brain" |

## Buyers

| Segment | Who signs |
|---|---|
| HK single-family offices with 1–5 finance people (beachhead) | CFO, principal |
| Multi-family offices, trust companies, private banks | COO / Head of Operations |
| HK SMEs and accounting firms with the same back office | Finance manager, partner |
| Accounting/bookkeeping firms (many client workspaces) | Partner |

Business model: SaaS per seat plus document-volume tiers. Accounting-firm plan. Land with invoice intake and controls, expand to reconciliation, audit packs, then **reports** (next step).

## Why it can win

| Criterion | Our angle | Risk → how we close it |
|---|---|---|
| Innovation | Not another OCR tool: a brain with **memory of expectations and decisions** and per-cell provenance | "Isn't this Dext/Hubdoc?" → show the question + decision + learn moment |
| Technical execution | Deterministic checks, staged writes, git-backed history, citation validator, OCR cache | "LLM wrapper?" → architecture slide: LLM reads and asks, code decides |
| Functionality | One continuous live flow on a full fake company | Cached run + backup video |
| Problem-solving | Named users (Grace, Jason), real family-office workflow, controls finance already requires | Real numbers from eval + timed test |
| Industry impact | Every company in the room has this back office; fraud angle (bank-change scams) is concrete | Sourced BEC loss figures |

Signal from past events: the iFX Cyprus 2026 overall winner came from the "Keep Money Safe" track. The Pearl River capital call hold (fake wire instructions on RMB 3.5M) is our moment in that space.

## Hard questions

| Question | Answer |
|---|---|
| "Isn't this just invoice OCR?" | OCR is the input. The product is the memory: what's expected, every decision and why, and where every number came from. |
| "Can an LLM be trusted with numbers?" | It never writes directly and never decides about money. Checks are plain code, every change is a diff a human approves, every cell cites its source. |
| "What if it reads a number wrong?" | Arithmetic and quotes are checked in code, the source quote sits next to every value, and a wrong value is one revert in the history. |
| "Where do reports come from?" | Next step. Once every number is traceable, reports are an easy add-on, and each report line will click back to its source. |
| "People don't write down reasons." | Trace asks at the moment it matters, once, and saves it. |
| "Why not AWS?" | Model-agnostic on purpose: customers pick the provider or private deployment they trust with financial data. |
| "Data privacy?" | The workspace stays with the customer; only the pages needed go to the model, and the provider is the customer's choice. |
| "Copilot in Excel?" | Copilot works inside one file. Trace works across all files, remembers expectations and decisions, and keeps the history. |

## Ask (Final)

3–5 HK family offices or multi-family offices from the expo floor as pilot partners, plus intros to finance teams willing to share anonymised document sets.
