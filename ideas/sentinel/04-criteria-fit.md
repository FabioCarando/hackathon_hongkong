# Why Sentinel Can Win

How the idea fits the competition criteria. See `COMPETITION_CRITERIA.md` for the source list.

## Fit with the theme and problem areas

"Build the Future of Finance with AI" asks for **a meaningful problem in financial services**. Sentinel covers two of the five listed problem areas directly (**compliance & operations**, **payments & fintech**) and touches two more (**trading & investing** through manipulation monitoring, **digital assets** through VASP buyers). It's one product, not a spread of ideas, but it is relevant to most of the brief.

## Fit with each criterion

| Criterion | Why the idea scores | Where it's weak / how to close it |
|---|---|---|
| **Innovation** | Most AML tools are either rule systems or black-box ML. Sentinel combines rules derived from the regulations with an agent that investigates alerts like an analyst would, and it links identities across accounts at signup. "AI checking AI" matches what the HKMA sandbox is exploring. | "Fraud detection" sounds familiar. Lead with what's new: **cited, explainable triage** and **identity linking**, not "we detect fraud". |
| **Technical execution** | A clear three-tier architecture with a reason behind each choice: deterministic scoring, LLM only where judgement is needed, RAG for citations. Real AWS depth (Bedrock, Knowledge Bases, Guardrails, Rekognition, Lambda, DynamoDB). | Risk of looking like a wrapper around an LLM. Show the architecture slide and explain *why the LLM is not the scorer*. |
| **Functionality** | The demo is one continuous story (signup → alert → investigation → report) and can run on a simulator with no external dependencies. | Many moving parts. Scope ruthlessly (P0 only by 17:00) and have a backup video. |
| **Problem-solving approach** | Named users (compliance analyst, MLRO), a measurable pain (alert workload, onboarding fraud), and a solution designed around the analyst's actual workflow. | Needs real numbers. Fill in the pitch-numbers table in `03-evaluation.md`. |
| **Industry impact** | The Final audience (brokers, PSPs, prop firms, VASPs) *is* the buyer. Compliance cost is a budgeted line item; regulators push for it. Clear SaaS model. | A crowded market with incumbents. Position on SME brokers, HK localisation and time to deploy. |

## Fit with the implicit criteria

- **AWS as title sponsor:** AWS is used in every part: Bedrock for reasoning and RAG, Rekognition for identity, serverless backend, immutable audit storage. Nothing is bolted on.
- **Industry audience:** the pitch speaks to how they buy: cost per alert, regulatory exposure, deployment inside their own AWS account.

## Fit with what separates the Top 7

| Separator | How Sentinel covers it |
|---|---|
| Named buyer + painful number | Head of Compliance at an SME broker; alert workload, "40 → 4 min" (to be measured) |
| Live demo + backup video | Self-contained simulator; video recorded by 19:00 |
| 10-second wow | Face dedupe links a "new" applicant to 2 existing accounts, live |
| HK/APAC localisation | SFC/AMLO/JFIU rules, FPS, Chinese-language STR draft (P2) |
| Guardrails + explainability | Every flag has a rule citation, confidence, and a human approval step; Bedrock Guardrails |
| Use the 5–7 Oct window | P2 list is ready: benchmarks, audit trail, deck, extra onboarding checks |
| Scope ruthlessly | P0/P1/P2/P3 labels in `02-implementation.md` |

## Signals from past events

- At **iFX Hack Cyprus 2026**, the overall winner came from the *"Keep Money Safe"* (fraud & security) track, ahead of the AI-trading track.
- The **HKMA GenAI Sandbox** (cohort 2) prioritises risk management, anti-fraud and deepfake defence, the same space as Sentinel.
- Winners at similar trading-industry hackathons (Quadcode 2024, Deriv 2026) had one clear flow that fit into the user's existing workflow and showed its value within seconds.

## Hard questions to prepare for

| Question | Short answer |
|---|---|
| "Where's your training data?" | We don't need history on day one: rules cover detection from the start. We prove detection on public labelled benchmarks and learn from analyst feedback. |
| "Why not just rules?" | Rules create the alert flood. The agent is what cuts the workload, and we measure that at fixed recall. |
| "Can an LLM be trusted with compliance?" | It never scores and never files. It investigates and drafts; every claim is tied to evidence; a human approves. |
| "What about data privacy?" | Deployable inside the broker's own AWS account; Guardrails redact PII. |
| "How is this different from incumbents?" | Built for SME brokers, localised for HK, explainable by design, and deploys in days. |
