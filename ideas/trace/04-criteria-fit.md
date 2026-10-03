# Why Trace Can Win

How the idea fits the competition criteria. See `COMPETITION_CRITERIA.md` for the source list.

## Fit with the theme and problem areas

"Build the Future of Finance with AI" asks for **a meaningful problem in financial services**. Trace sits in **compliance & operations** (finance back office, controls, audit support) and touches **payments & fintech** (holding suspicious payments). It's less about trading directly, so the pitch should note that brokers and fintechs in the audience have the same back office: vendor contracts, liquidity provider and SaaS invoices, forecasts.

## Fit with each criterion

| Criterion | Why the idea scores | Where it's weak / how to close it |
|---|---|---|
| **Innovation** | "Claude Code for finance" is a new, instantly understood category. Not another invoice tool or finance chatbot: an agent that does the work, with diffs, approval and git-like history of why. | Judges may hear "chatbot for Excel". Show the agent *doing* a task and the diff in the first 30 seconds. |
| **Technical execution** | A real agent loop with tools, staged edits, deterministic controls as hooks, git-backed history with per-cell sources. Each choice has a reason. | Risk of looking like an LLM wrapper. Show the architecture slide and explain *why the LLM never writes directly and never decides about money*. |
| **Functionality** | One continuous story on a self-contained fake workspace: update forecast → enter invoices → ask why. | Agent tasks can be slow or flaky live. Cap steps, pre-warm, cache the demo run, backup video. |
| **Problem-solving approach** | Named user (finance manager at an HK SME), concrete pains (manual entry, scattered documents, no history of why), and diff + approval matches how finance controls already work. | Needs real numbers. Fill in `03-evaluation.md`; ideally one quote from a real controller. |
| **Industry impact** | Every company in the audience has a finance team doing this work. Time saved and errors caught are measurable. Clear SaaS model, plus accounting firms as a multiplier channel. | Big players (Microsoft Copilot in Excel, accounting-software AI features) are moving here. Position on the agent + history + approval model, HK bilingual documents, and SMEs. |

## Fit with the implicit criteria

- **AWS is the title sponsor**, and we're building on OpenRouter instead. Expect the question. The answer: model-agnostic by design, so customers can run it with whichever provider or private deployment they trust.
- **Industry audience:** judges run companies with finance teams. They can picture their own controller using it on Monday.

## Fit with what separates the Top 7

| Separator | How Trace covers it |
|---|---|
| Named buyer + painful number | Finance manager at an HK trading SME; hours of manual entry, days of audit prep (to be measured) |
| Live demo + backup video | Self-contained fake workspace; video recorded by 19:00 |
| 10-second wow | "Update the forecast for the new lease" → a spreadsheet diff appears with a source on every cell |
| HK/APAC localisation | Chinese + English documents, HKD/RMB/USD, mainland supplier invoices |
| Guardrails + explainability | Nothing changes without approval; every cell has a source; controls are deterministic; full history |
| Use the 5–7 Oct window | P2 list is ready: task suite, benchmarks, audit pack export, xlsx download with cell notes |
| Scope ruthlessly | P0/P1/P2/P3 labels in `02-implementation.md` |

## Signals from past events

- At **iFX Hack Cyprus 2026**, the overall winner came from the *"Keep Money Safe"* (fraud & security) track. Trace's invoice holds give a moment in that space inside a broader product.
- Winners at similar trading-industry hackathons had one clear flow that fit the user's existing workflow and showed value within seconds. Trace works on the Excel files the user already has.

## Hard questions to prepare for

| Question | Short answer |
|---|---|
| "Isn't this Copilot in Excel?" | Copilot helps inside one file. Trace works across the whole finance workspace (PDFs, contracts, sheets, ledger), shows a reviewable diff, and remembers why every number changed. |
| "Can an LLM be trusted with financial numbers?" | It never writes directly: every change is a diff a human approves, every cell cites its source, and money checks are plain code, not the LLM. |
| "What if it gets a number wrong?" | You see it in the diff before it lands, with the source quote next to it. If it slips through, history shows exactly when and from where, and it's one revert. |
| "Why not just use Xero / our ERP?" | We sit beside it. Xero records transactions; it doesn't read the lease and update your forecast, or tell you why a number changed. |
| "Where does the 'why' come from? People don't write reasons down." | Every change made through Trace records its reason and source automatically. For older numbers it uses the evidence people already leave: emails, notes, comments. When nothing exists, it asks once, like a commit message. |
| "Why not AWS?" | Model-agnostic on purpose: customers choose the provider or private deployment they trust with financial data. |
| "What about data privacy?" | The workspace stays with the customer; only the pages needed for a task go to the model, and the provider is the customer's choice. |
