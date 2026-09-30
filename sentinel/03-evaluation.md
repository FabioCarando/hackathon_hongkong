# Evaluation Plan

Why this matters: judges will ask "where's your data?" and "how do you know it works?". This file answers both, and it produces the numbers used in the pitch.

**Framing:** no broker has labelled history when it first adopts a system like this. We **prove** detection on public labelled datasets, **demo** it on our own simulator, and **improve** it in production from analyst feedback.

## Datasets

| Dataset | Content | Use | Label |
|---|---|---|---|
| **SAML-D** (Oztas et al., 2023) | ~9.5M synthetic transactions, 28 typologies (17 suspicious) | Main AML benchmark, results per typology | P2 |
| **IBM AMLworld** (Altman et al., NeurIPS 2023) | Synthetic laundering patterns (fan-in/out, cycle, scatter-gather) | Graph-pattern benchmark | P2 |
| **PaySim** | 6.3M mobile-money transactions, fraud-labelled | Payments / account-takeover fraud | P3 |
| **Elliptic / Elliptic++** | Labelled Bitcoin transaction graph | Virtual-asset angle | P3 |
| **FaceForensics++ / Celeb-DF** | Deepfake face videos | Attack samples for onboarding | P2 |
| **MIDV-2020 / SIDTD** | Synthetic ID documents, including forgeries | ID-tampering checks | P3 |
| **ABIDES** | Agent-based market simulator | Generating trading-manipulation scenarios | P3 |
| **Our simulator** | Broker clients + injected scenarios | Live demo, detection per scenario | **P0** |

## Metrics

### Onboard

| Metric | How | Label |
|---|---|---|
| Face-dedupe precision / recall | 50 synthetic applicants, 8 of them reusing faces | **P0** |
| Liveness APCER / BPCER (ISO 30107-3 attack and false-rejection rates) | Attacks we create: screen replay, printed photo, deepfake clips | P2 |
| Latency per onboarding | Measured end to end | P1 |

### Monitor

| Metric | How | Label |
|---|---|---|
| Detection per injected scenario (yes/no, time to detect) | Simulator | **P0** |
| **PR-AUC, recall per typology, precision@k** | SAML-D, split by time to avoid leakage. **Never report accuracy** (positives are ~0.1%) | P2 |
| **Alert volume at fixed recall**, rules only vs full system | Headline number: "same recall, X% fewer alerts" | P1 on simulator · P2 on SAML-D |
| Agent: false-positive reduction at ≥95% recall of true positives | Proves the agent reduces workload without missing real cases | P1 |
| Agent: agreement with labels | On simulator and benchmark alerts | P1 |
| Agent stability | Same alert run 5×: how often the verdict stays the same | P1 |
| Cost and latency per investigated alert | $ and seconds | P1 |

### Resolve

| Metric | How | Label |
|---|---|---|
| Faithfulness: % of claims supported by the cited evidence | LLM judge + manual spot-check of 20 | P1 |
| Citation accuracy: does the cited SFC paragraph support the flag? | Manual check | P1 |
| STR completeness: % of required JFIU fields filled correctly | Checklist | P2 |
| Analyst time before/after | Team members time themselves on 5 alerts, manually vs with Sentinel | P1 (source of the "40 → 4" claim) |

## Numbers for the pitch

Fill these in as they're measured and put them on the metrics slide.

| Claim | Value | Source |
|---|---|---|
| Alerts reduced at the same recall | _TBD_ | simulator / SAML-D |
| Minutes per alert, manual → assisted | _TBD_ | timed test |
| Face-dedupe precision / recall | _TBD_ | synthetic applicants |
| Cost per investigated alert | _TBD_ | Bedrock usage |
| Faithfulness of explanations | _TBD_ | LLM judge + spot-check |
