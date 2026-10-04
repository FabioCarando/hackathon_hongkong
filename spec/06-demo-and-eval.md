# 06 · Demo and evaluation

## Demo script (3 min + 2 min Q&A)

Setup: reset demo, user = Ken Lau, `LLM_CACHE=on` with a pre-warmed cache, backup video ready.

| Time | Action | What the jury sees |
|---|---|---|
| 0:00 | Problem | "Finance teams retype PDFs into Excel, hunt for files, and nobody remembers why a number changed. Fraud slips in during routine work." One sourced number |
| 0:20 | **Files** page | "The brain knows every file: 41 contracts, invoices, statements, emails and sheets. 8 new since yesterday." |
| 0:35 | **Inbox** › Process new documents | Steps stream: 5 invoices read, 2 of them scanned, 1 in Chinese. 3 green cards, 2 red |
| 0:55 | Accept all clean | Diff → accepted → toast "Committed 3f2a1c0". Register rows appear, each with a source |
| 1:10 | Open the red Shenzhen Parts card ← **wow 1** | "Price 8.3% above contract. Bank account changed: …7731, but the last 6 payments went to …2049. Sent from shenzhen-parts.co, not shenzhenparts.com." Trace asks why. "Approve & remember" is locked: policy needs a call-back. Ken: **Reject**, "Not expected, calling supplier on known number" → logged D-0001 |
| 1:40 | Duplicate card | "Same as INV-2291 entered 3 Sep, still unpaid." Reject → logged |
| 1:55 | Lease card ← **wow 2** | "New lease signed 29 Sep: HK$82,400 from Jan 2027, +3%/yr. Your forecast assumes HK$80,000 (D. Wong, Aug). Update?" Switch user to Anna → Approve & remember → diff of 24 rent cells with lease p.3 §4 on each → commit |
| 2:20 | **Ask** › "Why is 2027 rent 82,400?" ← **wow 3** | Answer with chips: lease p.3 §4, Anna's decision today, the old Aug assumption commit. "A month from now, a new hire gets this in 5 seconds." |
| 2:40 | Close | Value line + ask (see `07`) |

Fallback: if the live LLM is slow, the cache replays. If wifi dies, play the video.

## Evaluation

`scripts/eval.py` runs the full pipeline on a fresh runtime copy (no UI) and compares against `workspace/ground_truth/expected.json`. Output: a table plus `logs/eval.json`. Run it with the real model before rehearsals and with `LLM_PROVIDER=fake` in CI only to check that it runs.

| Metric | How | Target | Label |
|---|---|---|---|
| **OCR/extraction field accuracy** | Inbox invoices: supplier_id, invoice_no, date, currency, amount, due_date, bank_account vs `tasks[1]` + planted evidence | ≥ 95% | **P0** |
| **Planted problems caught** | P1–P4 in `planted_problems` fire with the right control | 4/4 | **P0** |
| **False holds** | Holds on `clean_invoices` | 0 | **P0** |
| **Register end state** | Rows appended vs `tasks[1].rows` after the scripted decisions (reject both held) | exact | **P0** |
| **Forecast end state** | RENT_FORECAST vs `tasks[0].cells` | 24/24 | **P0** |
| **Every changed cell has a source** | `sources.json` coverage of cells changed by Trace commits | 100% | **P0** |
| "Why?" answer facts | `tasks[2].facts` covered (LLM judge or keyword check) + cites lease p.3 | ≥ 4/5 | P1 |
| Deadlines | `tasks[3]` | exact | P1 |
| Citation validity | % of answer refs that resolve | 100% | P1 |
| Learn-then-pass | Approve-and-remember a price change → re-run → no question | pass | P1 |
| Cost and time per document | From `logs/llm_calls.jsonl` | report | P1 |
| Manual vs Trace minutes | Team times itself: enter 5 invoices; find the support for 2027 rent | report | P1 (pitch number) |

## Numbers for the pitch

| Claim | Value | Source |
|---|---|---|
| Fields read correctly | _TBD_ | eval |
| Planted problems caught / false holds | _TBD_ | eval |
| Minutes per task, manual → Trace | _TBD_ | timed test |
| Changed cells with a source | _TBD_ | eval |
| Cost per document | _TBD_ | call log |

## Numbers to verify before going on stage

- [ ] Hours per week finance teams spend on manual entry
- [ ] Cost of processing one invoice manually vs automated (Ardent Partners / APQC)
- [ ] Business email compromise losses (FBI IC3; HK Police email scam figures)
- [ ] Time spent on audit support requests (ideally a quote from a real controller)
