"""JSON / JSONL files under the runtime workspace's .trace/ (atomic writes)."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.data import workspace


def _p(rel: str) -> Path:
    return workspace.trace_dir() / rel


def read_json(rel: str, default: Any = None) -> Any:
    p = _p(rel)
    return json.loads(p.read_text()) if p.exists() else default


def write_json(rel: str, data: Any) -> None:
    p = _p(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        text = data.model_dump_json(indent=2)
    elif isinstance(data, list) and data and isinstance(data[0], BaseModel):
        text = json.dumps([d.model_dump(mode="json") for d in data], indent=2, ensure_ascii=False)
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    fd, tmp = tempfile.mkstemp(dir=p.parent)
    with os.fdopen(fd, "w") as f:
        f.write(text + "\n")
    os.replace(tmp, p)


def read_jsonl(rel: str) -> list[dict]:
    p = _p(rel)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def append_jsonl(rel: str, record: BaseModel | dict) -> None:
    p = _p(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = record.model_dump_json() if isinstance(record, BaseModel) else json.dumps(record)
    with p.open("a") as f:
        f.write(line + "\n")


def cache_get(name: str) -> Any:
    """Result cached by content hash: runtime .trace/extracted/, then the shipped demo cache."""
    from app.config import settings

    for p in (_p(f"extracted/{name}"), Path(settings.trace_demo_cache) / name):
        if p.exists():
            return json.loads(p.read_text())
    return None


def cache_put(name: str, data: Any) -> None:
    write_json(f"extracted/{name}", data)
