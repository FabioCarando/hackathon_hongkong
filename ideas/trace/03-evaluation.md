# Evaluation Plan

Why this matters: judges will ask "does the agent actually get the numbers right?" and "how much time does it save?". This file answers both, and it produces the numbers used in the pitch.

**Framing:** coding agents are judged on task suites (does the code end up correct?). We do the same for finance: a suite of realistic tasks on our fake company where we know the correct end state of every spreadsheet. Public datasets back up document reading and cited answers.

## Datasets

| Dataset | Content | Use | Label |
|---|---|---|---|
| **Our fake workspace** | HK trading company: contracts, lease, ~20 invoices (EN + 中文), payments, forecast, budget, emails, planted problems | Live demo; task suite | **P0** |
| **Our task suite** | ~15 tasks with a known correct end state (e.g. "enter these invoices", "update forecast for the lease", "why is X?") | Task success rate | P1 (5 tasks) · P2 (15) |
| **FinanceBench** (Patronus AI, open sample of 150) | Questions over company filings with answers and evidence pages | Accuracy of cited answers | P2 |
| **DocILE** | Business documents (mostly invoices) with labelled fields | Invoice reading accuracy | P2 |
| **XFUND** | Forms in 7 languages including Chinese, labelled key-value pairs | Chinese reading accuracy | P2 |
| **CUAD** (Atticus Project) | 510 contracts, 41 labelled clause types incl. renewal, notice period, price changes | Contract clause finding | P3 |

## Metrics

### Doing the work

| Metric | How | Label |
|---|---|---|
| **Task success rate** | % of tasks where the spreadsheet ends in the correct state | P1 |
| **Cell accuracy** | % of proposed cell values that match ground truth | **P0** (on demo tasks) |
| Diffs accepted without edits | % of proposed change sets a reviewer accepts as-is | P1 |
| Steps and time per task | Tool calls and seconds per task | P1 |
| Cost per task | OpenRouter usage | P1 |
| Stability | Same task run 5×: how often the end state is the same | P2 |

### Noticing problems

| Metric | How | Label |
|---|---|---|
| **Planted problems caught** | Every planted problem: held yes/no | **P0** |
| False holds on clean invoices | Count holds on invoices with no planted problem | P1 |

### Remembering and explaining

| Metric | How | Label |
|---|---|---|
| "Why?" answer correctness | 10 "why is this number like this?" questions on the fake workspace, checked against history | P1 |
| Citation accuracy | Does each cited document/commit support the sentence? Manual check | P1 |
| Every changed cell has a source | % of committed cells with a valid source reference (target: 100%) | P1 |
| Cited-answer accuracy on FinanceBench sample | Answer + evidence page match | P2 |

### Time saved

| Metric | How | Label |
|---|---|---|
| Minutes per task, manual vs Trace | Team members time themselves on 3 tasks: entering 5 invoices, updating the forecast for the lease, answering "why did rent go up?" | P1 (source of the time claim) |

## Numbers for the pitch

Fill these in as they're measured and put them on the metrics slide.

| Claim | Value | Source |
|---|---|---|
| Task success rate | _TBD_ | task suite |
| Cell accuracy | _TBD_ | task suite |
| Planted problems caught / false holds | _TBD_ | fake workspace |
| Minutes per task, manual → Trace | _TBD_ | timed test |
| Changed cells with a source | _TBD_ | change log |
| Cost per task | _TBD_ | OpenRouter usage |
