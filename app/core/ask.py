"""Ask the brain: an agent over the workspace with tools; answers cite docs, commits, decisions."""

import json
import re
from datetime import date

from app.core import changes, decisions, indexer, reader, search, versioning
from app.core import expectations as ex
from app.data import sheets, workspace
from app.llm import AgentResult, get_llm, tool

TODAY = date(2026, 10, 5)

SYSTEM = f"""You are Trace, the finance team's brain at Harbour Lane Trading Ltd (Hong Kong). Today is \
{TODAY:%d %b %Y}. Answer questions about the team's files, numbers and decisions using the tools. Look \
things up; never guess. Answer in plain, short sentences for a finance manager (max ~6 sentences).

Cite every fact right after the sentence, using exactly these forms:
[doc: <workspace path> p.<page>]   e.g. [doc: docs/contracts/S04_lease_2027_signed.pdf p.3]
[commit: <7+ char hash>]            e.g. [commit: cbcb6ff]
[decision: D-0001]
For "why was this invoice held / what happened to document X" use processed_documents.
For "why is this cell X" questions use cell_history first: it lists every change, its reason, \
sources and commit. Rent forecast = sheets/forecast_2027_2028.xlsx, sheet Forecast, row 9 \
(C9 = Jan-27 ... Z9 = Dec-28). When explaining a number, also say what it was before, who \
decided the change and why (from cell_history / decisions).
Most questions need 1-3 tool calls. As soon as you have the facts, write the answer."""


@tool
def search_documents(query: str) -> str:
    """Full-text search over all documents (English and Chinese). Returns path, page and snippet."""
    return json.dumps(search.search(query), ensure_ascii=False)


@tool
def read_document(path: str, page: int | None = None) -> str:
    """Read a document's text (optionally one page). Path is workspace-relative."""
    rr = reader.read(path, ocr=False)
    pages = [p for p in rr.pages if page is None or p.page == page]
    return "\n\n".join(f"=== {path} p.{p.page} ===\n{p.text}" for p in pages)[:8000]


@tool
def cell_history(file: str, sheet: str, cell: str) -> str:
    """Every recorded change to a spreadsheet cell: value, reason, sources, commit, author, date."""
    keep = (
        "value",
        "reason",
        "sources",
        "decision",
        "commit",
        "commit_author",
        "commit_date",
        "commit_subject",
    )
    hist = versioning.history(file, sheet, cell.upper())
    return json.dumps([{k: e.get(k) for k in keep} for e in hist], ensure_ascii=False, default=str)


@tool
def read_sheet(file: str, sheet: str, cells: str) -> str:
    """Read a cell range, e.g. file='sheets/forecast_2027_2028.xlsx', sheet='Forecast', cells='C9:Z9'."""
    return json.dumps(sheets.read_range(file, sheet, cells), default=str)


@tool
def list_decisions() -> str:
    """Every decision the team made when Trace asked why, with reason and commit."""
    return json.dumps(
        [d.model_dump(mode="json") for d in decisions.all_decisions()], ensure_ascii=False
    )


@tool
def get_expectations(subject: str | None = None) -> str:
    """What the brain expects (contract prices, bank accounts, assumptions...). subject = S01..S05 or 'company'."""
    items = [e for e in ex.load() if subject is None or e.subject == subject]
    return json.dumps(
        [e.model_dump(mode="json", exclude_none=True) for e in items], ensure_ascii=False
    )


@tool
def list_files(kind: str | None = None) -> str:
    """The file index. kind = invoice | contract | email | sheet | ledger | bank_statement | memory."""
    return json.dumps(
        [
            {
                "path": f.path,
                "kind": f.kind,
                "status": f.status,
                "supplier": f.supplier_id,
                "pages": f.pages,
            }
            for f in indexer.load()
            if kind is None or f.kind == kind
        ]
    )


@tool
def contract_deadlines(within_days: int = 30) -> str:
    """Auto-renewing contracts whose cancellation deadline falls within the next N days."""
    items = ex.contract_deadlines(TODAY, within_days)
    for d in items:
        d["source"] = d["source"].model_dump(exclude_none=True)
    return json.dumps(items)


@tool
def git_log() -> str:
    """The workspace version history: commit hash, author, date, subject."""
    return json.dumps(
        [{k: c[k] for k in ("hash", "author", "date", "subject")} for c in workspace.log()]
    )


@tool
def processed_documents(search: str | None = None) -> str:
    """Documents Trace processed: status (held/accepted/rejected), what didn't fit (findings with
    numbers and evidence), the question asked and the decision. Optional text filter, e.g. 'Shenzhen'."""
    out = []
    for cs in changes.all_changesets():
        blob = f"{cs.title} {cs.trigger}"
        if search and search.lower() not in blob.lower():
            continue
        out.append(
            dict(
                id=cs.id,
                title=cs.title,
                doc=cs.trigger,
                status=cs.status,
                findings=[
                    dict(
                        control=f.control,
                        title=f.title,
                        detail=f.detail,
                        evidence=[e.model_dump(exclude_none=True) for e in f.evidence],
                    )
                    for f in cs.findings
                ],
                decision=cs.decision,
                decided_by=cs.decided_by,
                commit=cs.commit,
            )
        )
    return json.dumps(out, ensure_ascii=False, default=str)


TOOLS = [
    processed_documents,
    search_documents,
    read_document,
    cell_history,
    read_sheet,
    list_decisions,
    get_expectations,
    list_files,
    contract_deadlines,
    git_log,
]

REF_RE = re.compile(r"[\[【](doc|commit|decision):\s*([^\]】]+)[\]】]")


def ask(question: str, on_step=None) -> AgentResult:
    return get_llm().run_agent(
        question, tools=TOOLS, system=SYSTEM, max_turns=8, on_step=on_step, label="ask"
    )


def validate_ref(kind: str, value: str) -> bool:
    """Citation validator: does this reference exist?"""
    value = value.strip()
    if kind == "doc":
        path, _, page = value.partition(" p.")
        if not workspace.path(path).exists():
            return False
        n = reader.page_count(path)
        return not (page.isdigit() and n and int(page) > n)
    if kind == "commit":
        return bool(workspace.git("cat-file", "-t", value, check=False).strip() == "commit")
    if kind == "decision":
        return any(d.id == value for d in decisions.all_decisions())
    return False
