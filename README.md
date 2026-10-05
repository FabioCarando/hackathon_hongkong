# Trace

### The finance team's brain.

**Trace turns financial documents into controlled, traceable data — while remembering where every number came from, why it changed, and who approved it.**

Built for the **iFX Hackathon 2026 — Trading & Fintech, Hong Kong**.

---

## Overview

Finance teams still spend a surprising amount of time moving information manually between PDFs, emails, contracts and spreadsheets.

An invoice arrives. Someone reads it.  
They compare it with a contract.  
They check whether the amount looks right.  
They verify the bank details.  
They update Excel.  
And months later, nobody remembers **why that number changed**.

Trace turns this workflow into an auditable, human-controlled pipeline.

```text
Financial Document
        │
        ▼
┌───────────────────┐
│ Document Intake   │
│ PDF / Email / OCR │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Field Extraction  │
│ Amounts · Dates   │
│ Accounts · Terms  │
└─────────┬─────────┘
          │
          ▼
┌──────────────────────┐
│ Expectation Engine   │
│ Contracts · History  │
│ Policies · Memory    │
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     │           │
   MATCH      EXCEPTION
     │           │
     ▼           ▼
  Propose      Ask Why
  Change       / Block
     │           │
     └─────┬─────┘
           ▼
┌──────────────────────┐
│ Human Decision       │
│ Approve / Reject     │
│ Approve & Remember   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Versioned Workspace  │
│ Data + Source + Why  │
│ User + Decision      │
└──────────┬───────────┘
           │
           ▼
      Ask the Brain
```

The core principle is simple:

> **Every financial number should have a provenance trail.**

---

## The Problem

Small finance teams — particularly family offices, fund administrators and private investment structures — often operate across:

- invoices
- capital calls
- fee notices
- contracts and side letters
- leases
- bank statements
- emails
- Excel workbooks

This creates four recurring problems.

### Manual data entry

Financial information from PDFs and scanned documents is manually copied into spreadsheets.

### Fragmented evidence

Contracts, invoices and supporting documents live across folders, email and shared drives.

### Lost decision context

A spreadsheet records the current value, but rarely explains:

- where it came from,
- why it changed,
- who approved it,
- or what document justified the decision.

### Errors and fraud

Routine workflows make it easy to miss anomalies such as:

- changed bank details,
- duplicate invoices,
- contract overcharges,
- incorrect fee rates,
- unusual recurring amounts,
- or unexpected forecast changes.

---

# How Trace Works

Trace combines **document intelligence, deterministic controls, human approval and institutional memory**.

## 1. Document Intake

Trace accepts financial documents such as:

```text
PDF
Scanned PDF
Email
Invoice
Capital Call
Fee Notice
Contract
Lease
Statement
```

Documents are indexed and processed into structured financial information.

For scanned or unstructured documents, Trace uses multimodal LLM capabilities to extract the relevant fields.

Examples include:

```text
Counterparty
Invoice number
Document date
Currency
Amount
Due date
Bank account
Fee rate
Contract terms
```

Evidence is retained alongside extracted values.

---

## 2. Expectation Engine

Extraction alone is not enough.

Trace compares incoming information against what the organization already knows.

The expectation layer can contain:

```text
Contract prices
Fee rates
Known bank accounts
Known email domains
Recurring amounts
Approval thresholds
Forecast assumptions
Account codes
Contract terms
```

This allows Trace to distinguish between:

```text
"Here is a number."
```

and:

```text
"Here is a number that conflicts with the signed agreement."
```

---

## 3. Exception Detection

Each proposed change is evaluated before entering the financial workspace.

Examples:

### Bank account mismatch

```text
Incoming capital call
Account: ****7731

Previous verified account
Account: ****2049

→ PAYMENT BLOCKED
```

The document may still be entered into the register, but payment remains blocked until the required verification process is completed.

---

### Contract mismatch

```text
Invoice amount: HKD 9,680
Contract amount: HKD 8,800

Difference: +10%

→ HELD FOR REVIEW
```

Trace surfaces the relevant evidence and asks the user to decide.

---

### Duplicate detection

Repeated document identifiers or suspicious combinations of:

```text
counterparty + amount + date
```

can be stopped before entering the books.

---

## 4. Human-in-the-Loop Decisions

Trace deliberately does **not** autonomously overwrite financial records when something unexpected happens.

Instead, the user receives the proposed change, supporting evidence and detected issue.

They can:

```text
Reject
Approve once
Approve & remember
```

Every decision stores:

```text
Who decided
When
What changed
Why
Which evidence supported it
Which rule triggered
Which commit introduced the change
```

This turns operational decisions into structured institutional knowledge.

---

## 5. Memory

One of Trace's core concepts is that finance systems should learn from **explicit human decisions**, not silently from model output.

When a user chooses:

```text
Approve & remember
```

Trace can update its expectation memory.

For example:

```text
Old expected rent:
HKD 95,000

New signed lease:
HKD 98,800

Human decision:
Approved by Grace Lam

New expectation:
HKD 98,800 from January 2027
```

Future documents can now be evaluated against the updated expectation.

Policy constraints remain authoritative: sensitive changes such as bank-account modifications still require their prescribed verification process.

---

# Provenance

Trace is designed around **cell-level provenance**.

A financial value should not exist without an answer to:

> Where did this number come from?

A changed spreadsheet cell can be linked to:

```text
Spreadsheet cell
      │
      ├── Source document
      │      └── Page / evidence
      │
      ├── Extracted value
      │
      ├── Triggered controls
      │
      ├── Human decision
      │
      ├── Decision reason
      │
      └── Version commit
```

This creates an auditable chain from the current number back to the evidence that created it.

---

# Ask the Brain

Because documents, expectations, decisions and provenance are indexed together, users can query the workspace in natural language.

For example:

```text
Why is 2027 rental income for Flat 12A HKD 98,800?
```

Trace can reconstruct the answer from:

1. the signed lease,
2. the relevant clause,
3. the previous forecast assumption,
4. the human approval,
5. the resulting spreadsheet update.

The answer includes references to the underlying evidence.

This turns Trace from a document-processing tool into a **queryable institutional memory for finance**.

---

# Demo Scenario

The hackathon demo models a Hong Kong single-family office managing investment and property-related financial operations.

The workspace contains contracts, invoices, capital calls, statements, emails and spreadsheets.

A typical demo flow is:

```text
1. Upload financial documents
            ↓
2. Trace reads and extracts them
            ↓
3. Clean documents are proposed for entry
            ↓
4. Anomalies are detected
            ↓
5. User reviews evidence
            ↓
6. User approves or rejects
            ↓
7. Decisions are recorded
            ↓
8. Spreadsheet changes are committed
            ↓
9. Provenance is stored
            ↓
10. Ask Trace why any number exists
```

The demo specifically includes scenarios involving:

- multilingual/scanned documents,
- bank-account anomalies,
- contract price discrepancies,
- forecast updates,
- human approval,
- persistent decision memory,
- and provenance-backed natural-language questions.

---

# Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                     Streamlit UI                        │
│                                                         │
│   Inbox        Memory        Files       Ask the Brain  │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    Trace Core                           │
│                                                         │
│  Intake       Reader       Indexer       Changes        │
│                                                         │
│  Expectations              Decisions                    │
└───────────────┬───────────────────────┬─────────────────┘
                │                       │
                ▼                       ▼
┌────────────────────────┐   ┌──────────────────────────┐
│    Intelligence Layer  │   │     Financial Data       │
│                        │   │                          │
│ OpenRouter             │   │ CSV / spreadsheet data   │
│ Vision models          │   │ Sources                  │
│ Structured extraction  │   │ Expectations             │
│ Natural-language Q&A   │   │ Decision history         │
└────────────────────────┘   └────────────┬─────────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │ Versioned Workspace  │
                              │ + Git-like history   │
                              └──────────────────────┘
```

---

# Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Application UI | Streamlit |
| Data processing | Pandas / NumPy |
| Validation | Pydantic |
| LLM abstraction | OpenAI-compatible client |
| Primary LLM gateway | OpenRouter |
| Alternative provider | Amazon Bedrock |
| Document intelligence | Multimodal / vision LLMs |
| Graph capabilities | NetworkX |
| ML utilities | scikit-learn |
| Visualization | Plotly |
| Dependency management | uv |
| Testing | pytest |
| Linting | Ruff |
| Git hooks | pre-commit |
| Configuration | pydantic-settings / dotenv |

---

# Repository Structure

```text
ifx-hackathon-2026-hongkong/
│
├── app/
│   ├── core/              # Trace processing and decision logic
│   ├── data/              # Financial workspace abstractions
│   ├── llm/               # LLM provider layer
│   └── ui/                # Streamlit interface
│       └── views/
│
├── scripts/               # Environment, evaluation and demo utilities
├── spec/                  # Product and evaluation specifications
├── tests/                 # Automated tests
├── workspace/             # Immutable demo financial workspace
├── runtime/               # Runtime copy of the workspace
├── demo_cache/            # Pre-computed demo document processing
│
├── streamlit_app.py       # Application entry point
├── pyproject.toml         # Python project configuration
├── uv.lock                # Reproducible dependency lock
├── .env.example           # Environment configuration template
└── README.md
```

---

# Getting Started

## Requirements

- Python **3.12**
- `uv`
- Git
- OpenRouter API key for live LLM execution

Clone the repository:

```bash
git clone https://github.com/FabioCarando/ifx-hackathon-2026-hongkong.git
cd ifx-hackathon-2026-hongkong
```

Install the environment:

```bash
uv sync
```

Create the local configuration:

```bash
cp .env.example .env
```

Configure at least:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here

LLM_MODEL=openai/gpt-oss-120b
LLM_MODEL_FAST=openai/gpt-oss-20b
LLM_MODEL_VISION=google/gemini-2.5-flash
```

Then run:

```bash
uv run streamlit run streamlit_app.py
```

The application will be available locally on:

```text
http://localhost:8501
```

---

# Offline / Development Mode

Trace also supports a fake LLM provider for UI development and offline testing.

```bash
LLM_PROVIDER=fake uv run streamlit run streamlit_app.py
```

This makes it possible to work on the application without API credentials or model costs.

---

# Demo Reliability

Hackathon demos should not depend entirely on network availability.

Trace therefore separates the immutable demo workspace from runtime state:

```text
workspace/
      │
      │ Reset demo
      ▼
runtime/workspace/
```

The original workspace remains unchanged.

Known demo documents can also be pre-computed and cached, allowing the document-processing sequence to execute rapidly and deterministically during the presentation.

LLM responses can additionally use the disk cache:

```env
LLM_CACHE=on
```

This allows rehearsed requests to replay without additional cost or network dependency.

---

# Testing

Run the offline test suite:

```bash
uv run pytest -q
```

Trace also includes an evaluation pipeline:

```bash
uv run python scripts/eval.py
```

The evaluation compares the pipeline output against the expected ground truth.

Core evaluation targets include:

| Metric | Target |
|---|---:|
| OCR / extraction field accuracy | ≥ 95% |
| Planted critical problems detected | 2 / 2 |
| False holds on clean invoices | 0 |
| Register final state | Exact |
| Forecast cells correctly updated | 24 / 24 |
| Changed cells with provenance | 100% |
| Citation validity | 100% |
| Learn-then-pass behavior | Pass |

---

# Development Rules

The repository uses `uv` as the source of truth for the Python environment.

Always run commands through:

```bash
uv run ...
```

Do not install dependencies directly with `pip`.

Add dependencies using:

```bash
uv add <package>
```

Remove them using:

```bash
uv remove <package>
```

Do not manually edit `uv.lock`.

Before committing:

```bash
uv run pytest -q
uv run ruff check .
```

Optional pre-commit hooks:

```bash
uv run pre-commit install
```

---

# Design Principles

Trace is built around five principles.

### 1. Evidence before automation

LLMs can extract and reason, but financial changes must remain connected to their source evidence.

### 2. Human authority

Unexpected financial changes require explicit human decisions.

### 3. Deterministic controls where possible

Fraud and accounting controls should not depend exclusively on probabilistic model reasoning.

### 4. Memory from decisions

The system learns from explicit approved decisions rather than silently modifying its own rules.

### 5. Provenance by default

Auditability is not an additional reporting layer. It is part of the data model.

---

# Current Scope

Trace is a hackathon prototype focused on demonstrating the architecture and interaction model.

Implemented concepts include:

- document ingestion,
- OCR and structured extraction,
- multilingual financial documents,
- contract and expectation checks,
- anomaly detection,
- bank-detail controls,
- duplicate detection,
- human approval workflows,
- decision logging,
- expectation memory,
- spreadsheet updates,
- version history,
- per-value provenance,
- cited natural-language Q&A,
- deterministic demo reset,
- automated evaluation.

Potential next steps include:

- live email and drive connectors,
- bank feeds,
- accounting-system integrations,
- multi-user RBAC,
- configurable approval chains,
- financial reporting,
- audit-support exports,
- multi-entity workspaces,
- and payment-system integrations.

---

# Why Trace

Most automation tools answer:

> **"Can we extract this number?"**

Trace asks a harder set of questions:

> **Where did this number come from?**  
> **Does it make sense?**  
> **Who approved it?**  
> **Why did they approve it?**  
> **What changed because of it?**  
> **Can we prove all of that six months later?**

That is the difference between document automation and **financial memory**.

---

## iFX Hackathon 2026

**Trading & Fintech · Hong Kong**

Built as a working prototype during the iFX Hackathon 2026.

**Trace — every number has a story.**