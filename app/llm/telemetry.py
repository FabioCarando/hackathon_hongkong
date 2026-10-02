"""Per-call cost/latency log: kept in memory for the UI and appended to a JSONL file."""

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings


@dataclass
class CallStats:
    model: str
    label: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float | None = None
    cached: bool = False
    stop_reason: str | None = None
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


_lock = threading.Lock()
CALLS: list[CallStats] = []


def record(stats: CallStats) -> None:
    with _lock:
        CALLS.append(stats)
        path = Path(settings.llm_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(asdict(stats)) + "\n")


def totals() -> dict:
    with _lock:
        live = [c for c in CALLS if not c.cached]
        return {
            "calls": len(CALLS),
            "cached_calls": len(CALLS) - len(live),
            "input_tokens": sum(c.input_tokens for c in CALLS),
            "output_tokens": sum(c.output_tokens for c in CALLS),
            "cost_usd": sum(c.cost_usd or 0 for c in live),
            "avg_latency_ms": sum(c.latency_ms for c in live) / len(live) if live else 0.0,
        }


def reset() -> None:
    with _lock:
        CALLS.clear()
