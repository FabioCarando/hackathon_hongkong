# Practical Implementation

Guiding principle: **don't train new detectors.** Our value is in how existing tools are combined, in rules that trace back to the regulations, and in explainability. Reuse managed services wherever possible, and build only what differentiates us.

## Urgency labels

| Label | Deadline | Meaning |
|---|---|---|
| **P0** | ~17:00, 4 Oct | Core demo flow works end to end |
| **P1** | 21:00, 4 Oct (submission) | Polish and depth that raise the score |
| **P2** | 5–7 Oct (only if we reach the Top 7) | Benchmarks, audit trail, extra checks, deck |
| **P3** | Roadmap | Mentioned in the pitch only, not built |

> ⚠️ If building before 4 Oct is allowed (see `COMPETITION_CRITERIA.md`), move the simulator, rule catalog, and AWS/Bedrock setup to **pre-event** and shrink P0 accordingly.

## Architecture

```
                ┌──────────── ONBOARD ────────────┐
applicant ───►  │ Liveness · Face match · ID read │──► identity graph (face / device / phone)
                │ Face dedupe · Profile check     │            │
                └─────────────────────────────────┘            │
                                                                ▼
                ┌──────────── MONITOR ────────────────────────────────────────┐
events ──────►  │ T1 Rule engine (SFC-cited catalog) ─┐                        │
(simulator)     │ T2 Anomaly + graph features ────────┼─► risk score ─► top %  │
                │                                     │      ─► T3 Investigator agent (Bedrock + tools)
                └─────────────────────────────────────┴───────────────────────┘
                                                                ▼
                ┌──────────── RESOLVE ────────────┐
                │ Timeline · Cited explanation    │──► analyst approves ─► audit log
                │ STR draft (JFIU fields)         │
                └─────────────────────────────────┘
```

## AWS stack

| Need | Service |
|---|---|
| LLM reasoning, vision | **Amazon Bedrock** (Claude, via the Converse API) |
| Agent + tools | Bedrock AgentCore / Bedrock Agents, or the Strands Agents SDK |
| Regulation lookup (RAG) | **Bedrock Knowledge Bases** + S3 |
| Safety | **Bedrock Guardrails** (PII redaction, denied topics) |
| Liveness, face match, face dedupe | **Amazon Rekognition** (Face Liveness, `CompareFaces`, face collections + `SearchFacesByImage`) |
| Backend | Lambda + API Gateway (Step Functions if we want the workflow visible) |
| State, audit log | DynamoDB; S3 with Object Lock for immutable records |
| Frontend | Amplify (or a local app for the demo) |
| Dev speed | Kiro / Amazon Q Developer |

Notes:
- Textract `AnalyzeID` only supports US documents, so it can't read an HKID. Use Bedrock vision to extract ID data instead.
- Amazon Fraud Detector stopped accepting new customers in late 2025. Don't plan around it.

---

## 1. Onboard

**Approach:** reuse existing detectors and build our own layer that combines their results. The differentiator is **identity linking across accounts**: a deepfake may pass a single check, but mule rings reuse faces, devices and phone numbers across accounts.

| Component | Reuse or build | Label |
|---|---|---|
| Liveness / presentation-attack check (Rekognition Face Liveness) | Reuse | P1 (the liveness UI needs a web SDK; mock it on 4 Oct if it's slow to set up) |
| Selfie ↔ ID photo match (`CompareFaces`) | Reuse | P1 |
| ID field extraction (Bedrock vision) | Reuse | P2 |
| **Face dedupe across applicants** (face collection) | **Build** | **P0**: key demo moment |
| Profile consistency check (LLM compares declared profile with suitability expectations) | Build | P2 |
| Device / IP / phone graph | Build | P2 |
| Commercial-grade deepfake detection models | — | P3 |

## 2. Monitor

### Data

No history is needed on day one. **We treat cold start as a design requirement:** detection starts from rules and typologies, and the ML improves from analyst feedback. Public labelled datasets **prove** the detection works; our simulator **drives** the live demo.

| Component | Label |
|---|---|
| Broker event simulator (normal clients + injected scenarios: deposit→no trading→withdraw to a new account, mirrored trades between linked accounts, login burst from a new country, third-party deposits) | **P0** |
| SAML-D / IBM AMLworld benchmark runs | P2 |
| ABIDES-generated trading-manipulation scenarios (wash trades, matched orders) | P3 |

### Three tiers

The **LLM never does the scoring.** Scoring must be deterministic, cheap and auditable. The agent's job is **alert triage**, where the analyst cost actually sits.

| Tier | What | Label |
|---|---|---|
| **T1 Rule engine** | Runs the SFC rule catalog deterministically. Each hit carries its rule ID and source | **P0** (6–8 rules) |
| **T2 Anomaly / graph** | Per-client baselines (z-scores, Isolation Forest), graph features (shared devices, fund cycles, fan-in into one account) | P1 (z-scores) · P2 (graph, LightGBM on SAML-D) |
| **T3 Investigator agent** | Bedrock agent works on the top ~2–5% of alerts. Tools: client history, identity graph, KYC profile, rule lookup. Output: escalate or close, with its reasoning | **P0** (simple version) · P1 (all tools) |
| Learning from analyst feedback | Use analyst decisions as labels to retrain T2 | P3 |

### Bringing in the SFC: compiled offline, executed deterministically

1. **Sources:** SFC *Guideline on AML/CFT (for Licensed Corporations and SFC-licensed VASPs)* and its illustrative red-flag indicators; AMLO (Cap. 615); SFO market-misconduct provisions (false trading, wash trades); JFIU red-flag guidance. *Verify exact paragraph numbers before citing.*
2. **Offline:** the LLM extracts each red flag into a structured rule catalog, and a human reviews every rule.
3. **Runtime:** the rule engine executes the catalog. No LLM is involved in detection.
4. **At resolution:** RAG over the same source documents retrieves the exact paragraph for the explanation.
5. **Selling point:** when the SFC updates guidance, the LLM drafts the updated rules, a compliance officer approves them, and they're versioned.

Example rule:

```yaml
id: SFC-AML-RF-012
source: "SFC AML/CFT Guideline, para X.Y"   # verify
indicator: "Funds deposited and withdrawn with little or no trading activity"
condition: deposits_7d > 50000 AND trade_turnover_7d < 0.1 * deposits_7d AND withdrawal_to_new_acct
severity: high
typology: layering
```

| Component | Label |
|---|---|
| Hand-written catalog of 6–8 rules with source paragraphs | **P0** |
| Knowledge Base over SFC/AMLO documents for citations | P1 |
| LLM-assisted rule extraction with a human-review step | P2 |
| Automatic diff of regulatory updates → rule proposals | P3 |

## 3. Resolve

Summarising the timeline is easy. What makes the output credible is **faithfulness and an audit trail**.

| Component | Label |
|---|---|
| Alert timeline view | **P0** |
| Explanation where every sentence references event IDs and rule IDs | **P0** |
| STR draft mapped to JFIU STR fields | P1 |
| Validator that rejects any claim without a valid evidence reference | P1 |
| Human approve/reject step | **P0** (a button is enough) |
| Guardrails (PII redaction) | P1 |
| Audit record (input snapshot, rule version, model ID, prompt version, tool calls, analyst decision) in DynamoDB + S3 Object Lock | P2 |
| Chinese-language explanation / STR draft | P2 |

---

## Demo script (target 3 min)

1. **(0:00)** Problem in one sentence, with the painful number.
2. **(0:20)** New applicant signs up → **face dedupe links them to 2 existing accounts** ← wow moment
3. **(0:50)** Simulator runs → the deposit→withdraw mule pattern fires the SFC-cited rule.
4. **(1:20)** The agent investigates on screen (tool calls visible) → escalates. A second alert gets closed as a false positive.
5. **(2:00)** Resolve: timeline + cited explanation + STR draft → the analyst approves.
6. **(2:30)** Metrics slide (from `03-evaluation.md`), business model, ask.

## Timeline on 4 Oct

| Time | Goal |
|---|---|
| 09:30–10:30 | Kickoff, confirm rules and criteria, freeze scope, AWS access working |
| 10:30–14:00 | Simulator + rule engine + face dedupe, in parallel |
| 14:00–17:00 | Agent triage + Resolve view; **one full end-to-end flow by 17:00** |
| 17:00–19:00 | P1 items, UI polish, **record the backup video** |
| 19:00–21:00 | Pitch rehearsal ×3, submission |

## Risks

| Risk | Mitigation |
|---|---|
| Bedrock model access or quota not ready in the provided account | Check at kickoff; keep a personal account with access as a fallback |
| Rekognition Face Liveness UI takes too long to integrate | Use static images for face dedupe and mock liveness |
| Venue wifi fails during the demo | Backup video; a local simulator build |
| Agent is slow on stage | Pre-warm it; cap the number of tool calls; cache the demo scenario's results |
| Scope creep | Anything not P0 waits until the end-to-end flow works |
