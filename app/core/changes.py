"""Change sets: proposed writes a human accepts. Accepting writes the sheets, appends sources.json
and makes a git commit whose message is the reason and sources."""

from app.core import versioning
from app.core.models import ChangeSet, Decision
from app.data import sheets, store, workspace

DIR = "changesets"


def all_changesets() -> list[ChangeSet]:
    d = workspace.trace_dir() / DIR
    if not d.exists():
        return []
    return [ChangeSet.model_validate_json(p.read_text()) for p in sorted(d.glob("CS-*.json"))]


def get(cs_id: str) -> ChangeSet:
    return ChangeSet.model_validate(store.read_json(f"{DIR}/{cs_id}.json"))


def save(cs: ChangeSet) -> None:
    store.write_json(f"{DIR}/{cs.id}.json", cs)


def next_id(prefix: str, existing: list[str]) -> str:
    nums = [int(x.split("-")[1]) for x in existing if x.startswith(prefix)]
    return f"{prefix}-{max(nums, default=0) + 1:04d}"


def new_id() -> str:
    return next_id("CS", [cs.id for cs in all_changesets()])


def _comment(reason: str, sources) -> str:
    src = sources[0].label() if sources else ""
    return f"Trace: {reason}" + (f" — {src}" if src else "")


def apply(
    cs: ChangeSet, user: str, row_status: str | None = None, decision: Decision | None = None
) -> str:
    """Write the change set, record sources, commit. Returns the commit hash."""
    files: set[str] = set()
    entries: list[dict] = []
    for row in cs.new_rows:
        values = dict(row.values)
        if row_status:
            values["status"] = row_status
        r = sheets.append_row(row.file, row.sheet, values, _comment(row.reason, row.sources))
        files.add(row.file)
        entries.append(
            dict(
                file=row.file,
                sheet=row.sheet,
                cell=f"A{r}:L{r}",
                value=values.get("amount"),
                sources=[s.model_dump(exclude_none=True) for s in row.sources],
                reason=row.reason,
                decision=decision.id if decision else None,
                commit=None,
            )
        )
    for ch in cs.changes:
        values = {c: ch.new for c in sheets.cells_in(ch.cell)}
        sheets.write_cells(ch.file, ch.sheet, values, _comment(ch.reason, ch.sources))
        files.add(ch.file)
        entries.append(
            dict(
                file=ch.file,
                sheet=ch.sheet,
                cell=ch.cell,
                value=ch.new,
                old=ch.old,
                sources=[s.model_dump(exclude_none=True) for s in ch.sources],
                reason=ch.reason,
                decision=decision.id if decision else None,
                commit=None,
            )
        )
    if entries:
        versioning.add_sources(entries)
    return commit(cs, user, files, decision)


def commit(cs: ChangeSet, user: str, files: set[str], decision: Decision | None) -> str:
    save(cs)
    srcs = []
    for s in [s for r in cs.new_rows for s in r.sources] + [
        s for c in cs.changes for s in c.sources
    ]:
        line = f"- {s.label()}" + (f': "{s.quote}"' if s.quote else "")
        if line not in srcs:
            srcs.append(line)
    body = cs.reason
    if decision:
        body += f"\n\nDecision {decision.id} ({decision.answer.replace('_', ' ')}, {decision.by}): {decision.reason}"
    if srcs:
        body += "\n\nSources:\n" + "\n".join(srcs[:12])
    trace = [f".trace/{DIR}/{cs.id}.json", ".trace/sources.json"]
    for extra in (".trace/decisions.jsonl", ".trace/expectations.json"):
        if (workspace.root() / extra).exists():
            trace.append(extra)
    subject = cs.title if not decision else f"{cs.title} [{decision.id}]"
    h = workspace.commit([*sorted(files), cs.trigger, *trace], subject, body, user)
    versioning.set_commit(h)
    cs.commit = h
    save(cs)
    return h
