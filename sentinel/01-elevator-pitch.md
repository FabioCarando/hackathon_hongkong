# Elevator Pitch — Sentinel

> Working name. Replace it freely.

**One line:** an AI fraud and compliance copilot for online brokers. It stops fake and mule accounts at signup, flags suspicious activity with the exact SFC rule it breaks, and drafts the report for the regulator.

## 30-second script

> "Online brokers in Hong Kong face two costly problems: fraudsters opening accounts with deepfaked IDs and mule identities, and compliance teams buried in thousands of false-positive alerts. Every miss can mean a regulator fine, and every alert still costs an analyst half an hour.
>
> Sentinel is an AI copilot that sits on a broker's onboarding and transaction flow. It catches synthetic and deepfake identities at signup and scores suspicious trading and payments in real time. For each alert it writes an explanation citing the exact SFC or AML rule, plus a ready-to-file suspicious transaction report draft.
>
> Analysts go from 40 minutes per alert to 4. Built on AWS Bedrock with guardrails, so every decision is explainable and auditable. We sell it per seat to brokers, payment firms and prop firms."

## Problem

- **Deepfake and synthetic-identity fraud at onboarding** is growing. The HKMA names deepfake fraud as an emerging risk (GenAI Sandbox, cohort 2).
- **Mule accounts and scam proceeds** pass through retail broker and payment accounts, which creates AML exposure for the firm.
- **Transaction monitoring is rule-based and noisy.** Most alerts are false positives, analysts burn their time on them, and the backlog itself becomes regulatory risk.
- **Suspicious transaction reports (STRs) are written by hand**, which is slow and gives inconsistent quality.

## Buyers

| Segment | Pain | Who signs |
|---|---|---|
| Retail FX/CFD and securities brokers | KYC fraud, AML fines, analyst cost | Head of Compliance / MLRO, COO |
| Payment providers / PSPs | Mule accounts, chargebacks, scam flows | Head of Risk |
| Prop trading firms | Multi-accounting, identity abuse | Founder / Ops lead |
| SFC-licensed virtual-asset platforms | Strict AML and Travel Rule expectations | Compliance lead |

**Beachhead:** small and mid-size HK/APAC brokers. They are too small for enterprise suites such as NICE Actimize or ComplyAdvantage, but face the same SFC scrutiny as large firms.

## Solution: three moments

1. **Onboard:** document + liveness + face checks. It flags deepfakes and synthetic profiles, and links the new applicant to other accounts that share the same face, device or phone.
2. **Monitor:** trades and payments are scored live against SFC-cited rules and behavioural anomalies. An AI agent investigates the top alerts and closes the false positives.
3. **Resolve:** a timeline plus a cited explanation, then a one-click STR draft. A human approves; the AI never files anything automatically.

## Why now

- The HKMA and SFC are actively encouraging responsible GenAI adoption.
- Deepfake tooling is cheap, so onboarding attacks are scaling.
- Amazon Bedrock lets the system run inside the broker's own AWS account, so client data never leaves it. That removes a common compliance objection.

## Differentiation

- **Explainable by design:** every flag carries a regulation citation, a confidence score and an audit trail.
- **Built for HK:** SFC/HKMA rulebooks, Chinese and English, HK payment rails (FPS).
- **Works from day one:** it detects with rules derived from the regulations before any history exists, and improves from analyst feedback.
- **Plugs in:** connects by API or webhook, so there is no rip-and-replace of the broker's CRM or back office.

## Business model

- SaaS: a fee per analyst seat, plus a fee per onboarding check.
- Land with onboarding checks (fastest ROI), then expand into monitoring and STR drafting.

## Ask (Final)

- 2–3 brokers from the expo floor as pilot partners.
- AWS credits and a path into AWS Marketplace.

## Closing line

> "Fraudsters use AI to open accounts. Brokers should use AI to stop them, and to explain why to the regulator."

## Numbers to verify before going on stage

Judges will ask where the numbers come from. Use sourced figures, or a quote from a real compliance professional.

- [ ] False-positive rate of rule-based transaction monitoring (commonly cited as 90%+; find a source)
- [ ] Minutes an analyst spends per alert (the "40 → 4" claim; ideally measured by us, see `03-evaluation.md`)
- [ ] HK deception and scam losses for the latest year (HK Police annual figures)
- [ ] One example of an SFC enforcement action or fine for AML failures at a licensed firm
