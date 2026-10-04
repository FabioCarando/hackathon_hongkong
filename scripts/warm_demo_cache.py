"""Pre-compute the demo documents once with the real models and ship the results in demo_cache/
(OCR text, extracted fields and Trace's question wording, keyed by file content hash).
"Process new documents" then takes seconds and makes no LLM call for these files; any other
document still goes to the LLM. Rerun after regenerating the workspace (hashes change).

    uv run python scripts/warm_demo_cache.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
tmp = tempfile.mkdtemp(prefix="trace-warm-")
os.environ["TRACE_WORKSPACE"] = str(Path(tmp) / "workspace")
os.environ["TRACE_DEMO_CACHE"] = str(Path(tmp) / "none")  # compute fresh, don't read old results

from app.config import settings  # noqa: E402
from app.core import intake  # noqa: E402
from app.data import workspace  # noqa: E402
from app.llm import telemetry  # noqa: E402


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "demo_cache"
    workspace.reset()
    css = intake.process_inbox("Jason Yip", on_step=lambda s: print("  ·", s))
    produced = sorted((workspace.trace_dir() / "extracted").glob("*.json"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    for p in produced:
        shutil.copy(p, out / p.name)
    t = telemetry.totals()
    print(
        f"\n{len(css)} documents → {len(produced)} cached results in {out.name}/ "
        f"({t['calls']} LLM calls, ${t['cost_usd']:.4f}, models {settings.llm_model} / "
        f"{settings.llm_model_vision})"
    )
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
