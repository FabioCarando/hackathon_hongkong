"""Per-cell provenance (sources.json) and history / blame lookups joined with git."""

from openpyxl.utils import range_boundaries

from app.data import store, workspace

SOURCES = "sources.json"


def add_sources(entries: list[dict]) -> None:
    store.write_json(SOURCES, store.read_json(SOURCES, []) + entries)


def set_commit(commit: str) -> None:
    """Fill in the commit hash on entries appended before the commit was made."""
    entries = store.read_json(SOURCES, [])
    for e in entries:
        if e.get("commit") is None:
            e["commit"] = commit
    store.write_json(SOURCES, entries)


def _covers(ref: str, cell: str) -> bool:
    c1, r1, c2, r2 = range_boundaries(ref if ":" in ref else f"{ref}:{ref}")
    cc, rr, _, _ = range_boundaries(f"{cell}:{cell}")
    return c1 <= cc <= c2 and r1 <= rr <= r2


def commit_info(h: str) -> dict:
    out = workspace.git(
        "show",
        "-s",
        "--format=%H%x1f%an%x1f%ad%x1f%s%x1f%b",
        "--date=format:%Y-%m-%d %H:%M",
        h,
        check=False,
    )
    if not out:
        return {}
    parts = out.split("\x1f")
    return dict(
        hash=parts[0], author=parts[1], date=parts[2], subject=parts[3], body=parts[4].strip()
    )


def history(file: str, sheet: str, cell: str) -> list[dict]:
    """Every recorded change to this cell, newest first."""
    hits = [
        e
        for e in store.read_json(SOURCES, [])
        if e["file"] == file and e["sheet"] == sheet and _covers(e["cell"], cell)
    ]
    out = []
    for e in hits:
        info = commit_info(e["commit"]) if e.get("commit") else {}
        out.append({**e, **{f"commit_{k}": v for k, v in info.items()}})
    out.sort(key=lambda x: x.get("commit_date", ""), reverse=True)
    return out


def for_commit(h: str) -> list[dict]:
    return [e for e in store.read_json(SOURCES, []) if (e.get("commit") or "").startswith(h)]
