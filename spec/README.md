# Trace: build spec

**This directory is the single source of truth for what we build.** It replaces the old `ideas/trace/` notes (deleted; see git history). If code and spec disagree, the spec wins, or the spec gets updated first.

**Trace in one line:** a "team brain" for a small finance team. It knows where every file is, reads every document (OCR included), writes the useful numbers into the team's own spreadsheets, remembers what is *expected*, asks a human when something doesn't fit, and keeps a version history that records why each change was made.

Reports (P&L, cash flow, etc.) are a **next step**. They come once the brain works perfectly. They are not in this build.

## Read order

| File | What it answers | Read it when |
|---|---|---|
| [01-product.md](01-product.md) | What Trace is, for whom, which pains, what's in and out of scope | Always first |
| [02-workspace-data.md](02-workspace-data.md) | The fake company, every file in `workspace/`, planted problems, ground truth | Before touching data or writing checks |
| [03-architecture.md](03-architecture.md) | Modules, data models, storage, LLM use, the rules the code must follow | Before writing code |
| [04-features.md](04-features.md) | Every feature with priority (P0–P3) and acceptance criteria | Picking what to build next |
| [05-ui.md](05-ui.md) | Screens, layout, what each panel shows | Building the UI |
| [06-demo-and-eval.md](06-demo-and-eval.md) | The 3-minute demo script, metrics, eval script | Testing and rehearsing |
| [07-pitch.md](07-pitch.md) | Pitch, competition fit, hard questions | Preparing slides and Q&A |
| [08-build-plan.md](08-build-plan.md) | Ordered build steps, definition of done, repo rules | **"One-shot this"**: start here after 01 |

## Instructions for a coding agent ("one-shot this")

1. Read `01`, then `03`, `04` and `08` fully. Skim `02` and `05`, then go back to them when you need details.
2. Follow `08-build-plan.md` step by step. Build all **P0** items first, end to end, before any P1.
3. Check your work against `workspace/ground_truth/expected.json` using the eval in `06`. A P0 item is done only when its acceptance criteria in `04` pass.
4. Never edit `workspace/` directly from the app. The app works on a runtime copy (see `03` › Storage).
5. If the spec is ambiguous, pick the simplest option that keeps the demo in `06` working and write the choice into the relevant spec file.

## Fixed decisions (don't reopen)

- Single product: Trace. No other ideas.
- LLM through **OpenRouter** via the existing wrapper in `app/llm/`. No AWS/Bedrock in the plan.
- UI in **Streamlit** (team has little frontend experience). Polish beats breadth.
- The team's own spreadsheets (xlsx/CSV) are the system of record. **No external ERP or accounting system.**
- **The LLM never decides whether money is at risk.** Checks are plain code. The LLM reads, extracts, explains and asks.
- **Nothing is written without human approval.** Every write is a proposed change set, and accepting it creates a git commit with the reason and sources.
- Plain, non-technical language in anything a judge or user sees.
