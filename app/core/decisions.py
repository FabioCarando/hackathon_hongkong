"""Answers to Trace's questions: logged as decisions, committed, and (if asked) remembered."""

import re
from datetime import datetime

from app.core import changes
from app.core import expectations as ex
from app.core.intake import GUARDED
from app.core.models import Answer, ChangeSet, Decision
from app.data import store

FILE = "decisions.jsonl"
CALLBACK_RE = re.compile(r"call[\s-]?back|called|phoned|rang|by phone", re.I)


class PolicyError(ValueError):
    pass


def all_decisions() -> list[Decision]:
    return [Decision.model_validate(d) for d in store.read_jsonl(FILE)]


def _rewrite(items: list[Decision]) -> None:
    p = store._p(FILE)
    p.write_text("".join(d.model_dump_json() + "\n" for d in items))


def guard(cs: ChangeSet, answer: Answer, reason: str) -> None:
    if not reason.strip():
        raise PolicyError("A reason is required.")
    controls = {f.control for f in cs.findings}
    if answer == "approve_and_remember" and controls & GUARDED and not CALLBACK_RE.search(reason):
        raise PolicyError(
            cs.question.blocked_options_reason if cs.question else "Call-back needed."
        )


def accept(cs_id: str, user: str) -> str:
    """Accept a clean (proposed) change set as is."""
    cs = changes.get(cs_id)
    cs.status, cs.decided_by = "accepted", user
    return changes.apply(cs, user, row_status="Entered")


def reject_clean(cs_id: str, user: str) -> None:
    cs = changes.get(cs_id)
    cs.status, cs.decided_by = "rejected", user
    changes.save(cs)


def decide(cs_id: str, answer: Answer, reason: str, user: str) -> tuple[Decision, str]:
    cs = changes.get(cs_id)
    guard(cs, answer, reason)
    d = Decision(
        id=changes.next_id("D", [x.id for x in all_decisions()]),
        at=datetime.now(),
        by=user,
        changeset_id=cs.id,
        answer=answer,
        reason=reason.strip(),
        findings=[f.control for f in cs.findings if f.severity != "approval"],
    )
    if answer == "approve_and_remember":
        learned = [e.model_copy(update={"learned_from": d.id}) for e in cs.memory_updates]
        ex.upsert(learned)
        d.memory_updates = [e.id for e in learned]
    elif answer == "reject" and cs.reject_memory:  # e.g. remember a fraud sender / bank account
        learned = [
            e.model_copy(
                update={"learned_from": d.id, "note": f"{e.note or ''} Reason: {d.reason}".strip()}
            )
            for e in cs.reject_memory
        ]
        ex.upsert(learned)
        d.memory_updates = [e.id for e in learned]
    store.append_jsonl(FILE, d)

    cs.decided_by, cs.decision = user, d.id
    if answer == "reject":
        cs.status = "rejected"
        if cs.kind == "invoice":  # keep it traceable: written as HELD, never payable
            h = changes.apply(cs, user, row_status="HELD", decision=d)
        else:
            cs.new_rows, cs.changes = [], []
            h = changes.apply(cs, user, decision=d)
    elif answer == "approve_once" and cs.kind == "email":
        cs.status = "accepted"  # acknowledged, nothing written to the master
        cs.changes = []
        h = changes.apply(cs, user, decision=d)
    else:
        cs.status = "accepted"
        h = changes.apply(cs, user, row_status="Entered", decision=d)

    d.commit = h
    _rewrite([d if x.id == d.id else x for x in all_decisions()])
    if d.memory_updates:  # the brain learned something: re-check what is still open
        from app.core import intake

        intake.recheck_open()
    return d, h
