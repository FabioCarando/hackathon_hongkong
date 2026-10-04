"""The file index: every workspace file with kind, supplier, status and where it is used."""

import hashlib
import re
from pathlib import Path

from app.core import reader
from app.core.models import FileEntry
from app.data import sheets, store, workspace

KINDS = {
    "docs/invoices": "invoice",
    "docs/contracts": "contract",
    "docs/bank": "bank_statement",
    "docs/emails": "email",
    "sheets": "sheet",
    "ledger": "ledger",
}
GENERIC_PREFIXES = {"INV", "DN", "CN", "MF", "PO"}


def _kind(rel: str) -> str:
    if rel == "COMPANY.md":
        return "memory"
    return next((k for prefix, k in KINDS.items() if rel.startswith(prefix)), "other")


def supplier_hints() -> dict[str, list[str]]:
    """Filename hints per counterparty, from the master list and the register: the id, the first
    word of the name, the email domain's first label and the letters that start its document numbers."""
    prefixes: dict[str, set[str]] = {}
    for r in sheets.register():
        if m := re.match(r"[A-Za-z]{3,}", str(r["invoice_no"])):
            if m.group(0).upper() not in GENERIC_PREFIXES:
                prefixes.setdefault(r["supplier_id"], set()).add(m.group(0))
    out = {}
    for s in sheets.suppliers():
        hints = [s["id"], s["name_en"].split()[0], str(s["email_domain"]).split(".")[0]]
        out[s["id"]] = [h for h in hints if len(h) >= 3] + sorted(prefixes.get(s["id"], ()))
    return out


def _supplier(rel: str, hints: dict[str, list[str]]) -> str | None:
    name = Path(rel).name.lower()
    for sid, words in hints.items():
        if any(h.lower() in name for h in words):
            return sid
    return None


def _changeset_status() -> dict[str, tuple[str, str]]:
    """trigger doc -> (status, title) of its latest change set."""
    from app.core import changes

    return {cs.trigger: (cs.status, cs.title) for cs in changes.all_changesets()}


def build() -> list[FileEntry]:
    ws = workspace.root()
    new = workspace.untracked()
    commits = workspace.last_commits()
    cs_status = _changeset_status()
    hints = supplier_hints()
    used: dict[str, list[str]] = {}
    for entry in store.read_json("sources.json", []):
        ref = f"{entry['file']}!{entry['sheet']}!{entry['cell']}"
        for s in entry.get("sources", []):
            if s.get("doc"):
                used.setdefault(s["doc"], []).append(ref)
    for r in sheets.register():
        if r.get("source_file"):
            used.setdefault(r["source_file"], []).append(
                f"sheets/invoice_register.xlsx!Register!A{r['_row']}:L{r['_row']}"
            )

    out = []
    for p in sorted(ws.rglob("*")):
        rel = p.relative_to(ws).as_posix()
        if (
            not p.is_file()
            or rel.startswith((".trace/", "ground_truth/"))
            or p.name.startswith("~$")
        ):
            continue
        if rel == ".gitignore":
            continue
        status = "new" if rel in new else "tracked"
        title = p.stem.replace("_", " ")
        if rel in cs_status:
            s, title = cs_status[rel]
            status = {"accepted": "processed", "held": "held", "rejected": "held"}.get(s, "read")
        hit = reader.cached(rel) if reader.can_read(rel) else None
        method = "none"
        if hit and hit.pages:
            method = hit.pages[0].method
        elif rel.endswith(".pdf"):
            method = "vision_ocr" if reader.needs_ocr(rel) else "text_layer"
        elif reader.can_read(rel):
            method = "native"
        out.append(
            FileEntry(
                path=rel,
                kind=_kind(rel),
                sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                size=p.stat().st_size,
                pages=reader.page_count(rel),
                supplier_id=_supplier(rel, hints),
                title=title,
                status=status,
                text_method=method,
                last_commit=commits.get(rel),
                used_in=sorted(set(used.get(rel, []))),
            )
        )
    store.write_json("index.json", [e.model_dump(mode="json") for e in out])
    return out


def load() -> list[FileEntry]:
    return [FileEntry.model_validate(e) for e in store.read_json("index.json", [])]
