"""Run the full Trace pipeline on a fresh runtime copy (no UI) and score it against
workspace/ground_truth/expected.json. Prints the P0 metrics table and writes logs/eval.json.

    uv run python scripts/eval.py            # real models (needs .env)
    LLM_CACHE=on uv run python scripts/eval.py   # replays cached calls
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TRACE_WORKSPACE", "runtime/eval_workspace")

from app.core import changes, decisions, intake, versioning  # noqa: E402
from app.data import sheets, store, workspace  # noqa: E402
from app.llm import telemetry  # noqa: E402

GT = json.loads(Path("workspace/ground_truth/expected.json").read_text())
FIELDS = ["supplier_id", "invoice_no", "date", "currency", "amount", "due_date"]


def main() -> None:
    t0 = time.perf_counter()
    workspace.reset()
    css = intake.process_inbox("Ken Lau", on_step=lambda s: print("  ·", s))
    by_doc = {cs.trigger: cs for cs in css}
    results = []

    # 1. extraction field accuracy (inbox invoices vs tasks[1] rows + bank account)
    right = total = 0
    misses = []
    for exp in GT["tasks"][1]["expected"]["rows"]:
        cs = by_doc.get(exp["source_file"])
        inv = cs.invoice if cs else None
        got = {
            "supplier_id": inv and inv.supplier_id,
            "invoice_no": inv and inv.invoice_no,
            "date": inv and inv.invoice_date.isoformat(),
            "currency": inv and inv.currency,
            "amount": inv and inv.total,
            "due_date": inv and inv.due_date and inv.due_date.isoformat(),
        }
        for f in FIELDS:
            total += 1
            ok = (
                abs(float(got[f] or 0) - exp[f]) < 0.01
                if isinstance(exp[f], float)
                else got[f] == exp[f]
            )
            right += ok
            if not ok:
                misses.append(f"{exp['invoice_no']}.{f}: {got[f]!r} != {exp[f]!r}")
    for p in GT["planted_problems"]:
        if p["control"] == "BANK-001":
            inv = by_doc[p["invoice_file"]].invoice
            total += 1
            ok = (inv.bank_account or "").replace(" ", "") == p["evidence"][
                "invoice_bank_account"
            ].replace(" ", "")
            right += ok
            if not ok:
                misses.append(f"bank_account: {inv.bank_account!r}")
    acc = right / total
    results.append(("Extraction field accuracy", f"{right}/{total} = {acc:.0%}", acc >= 0.95))

    # 2. planted problems caught, 3. false holds
    caught = sum(
        any(f.control == p["control"] for f in by_doc[p["invoice_file"]].findings)
        for p in GT["planted_problems"]
        if p["invoice_file"] in by_doc
    )
    n = len(GT["planted_problems"])
    results.append(("Planted problems caught", f"{caught}/{n}", caught == n))
    false_holds = sum(by_doc[d].status == "held" for d in GT["clean_invoices"] if d in by_doc)
    results.append(("False holds on clean invoices", str(false_holds), false_holds == 0))

    # scripted decisions (the demo): accept clean, reject both held, approve the lease
    for cs in css:
        if cs.status == "proposed":
            decisions.accept(cs.id, "Ken Lau")
        elif cs.kind == "invoice":
            decisions.decide(cs.id, "reject", "Not expected (eval)", "Ken Lau")
        else:
            decisions.decide(cs.id, "approve_and_remember", "Lease signed (eval)", "Anna Chan")

    # 4. register end state
    rows = {r["invoice_no"]: r for r in sheets.register() if r["_row"] >= 19}
    exp_rows = GT["tasks"][1]["expected"]["rows"]
    ok_rows = 0
    for e in exp_rows:
        r = rows.get(e["invoice_no"])
        if r and all(
            (
                abs(float(r[k]) - e[k]) < 0.01
                if isinstance(e[k], float)
                else str(r[k])[:10] == str(e[k])[:10]
            )
            for k in (
                "date",
                "supplier_id",
                "currency",
                "amount",
                "fx_rate",
                "amount_hkd",
                "account_code",
                "due_date",
                "status",
                "source_file",
            )
        ):
            ok_rows += 1
    exact = ok_rows == len(exp_rows) and len(rows) == len(exp_rows)
    results.append(("Register end state", f"{ok_rows}/{len(exp_rows)} rows exact", exact))

    # 5. forecast end state
    cells = sheets.read_range("sheets/forecast_2027_2028.xlsx", "Forecast", "C9:Z9")
    exp_cells = GT["tasks"][0]["expected"]["cells"]
    ok_cells = sum(abs((cells[c] or 0) - v) < 0.01 for c, v in exp_cells.items())
    results.append(
        ("Forecast end state", f"{ok_cells}/{len(exp_cells)}", ok_cells == len(exp_cells))
    )

    # 6. every cell changed by a Trace commit has a source
    entries = [e for e in store.read_json("sources.json", []) if e.get("commit")]
    trace_commits = {cs.commit for cs in changes.all_changesets() if cs.commit}
    mine = [e for e in entries if e["commit"] in trace_commits]
    sourced = sum(bool(e.get("sources")) for e in mine)
    results.append(
        ("Changed cells with a source", f"{sourced}/{len(mine)}", sourced == len(mine) > 0)
    )

    hist = versioning.history("sheets/forecast_2027_2028.xlsx", "Forecast", "C9")
    blame_ok = len(hist) >= 2 and hist[0]["sources"][0].get("page") == 3
    results.append(("Blame C9: lease p.3 + old commit", f"{len(hist)} entries", blame_ok))

    t = telemetry.totals()
    print(f"\n{'Metric':38} {'Result':24} Pass")
    for name, value, ok in results:
        print(f"{name:38} {value:24} {'✅' if ok else '❌'}")
    print(
        f"\nLLM calls {t['calls']} ({t['cached_calls']} cached) · cost ${t['cost_usd']:.4f} · "
        f"{time.perf_counter() - t0:.0f}s total"
    )
    for m in misses:
        print("  miss:", m)
    Path("logs").mkdir(exist_ok=True)
    Path("logs/eval.json").write_text(
        json.dumps(
            {
                "results": [dict(metric=a, value=b, ok=c) for a, b, c in results],
                "misses": misses,
                "llm": t,
            },
            indent=2,
        )
    )
    sys.exit(0 if all(ok for *_, ok in results) else 1)


if __name__ == "__main__":
    main()
