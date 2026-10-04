"""Document -> pages of text. Text layer first; scanned pages go to the vision model. Cached by
sha256 in .trace/extracted/, so a second run makes no LLM call."""

import email
import hashlib
from email import policy
from functools import lru_cache
from pathlib import Path

import pymupdf

from app.config import settings
from app.core.models import PageText, ReadResult
from app.data import store, workspace

OCR_PROMPT = (
    "Transcribe all text on this scanned document page exactly as printed. Keep each table row on "
    "one line with cells separated by ' | '. Keep Chinese characters as they are. Keep all numbers, "
    "codes, dates, email addresses and bank account numbers exactly. Output only the transcription."
)


def sha256(rel: str) -> str:
    return hashlib.sha256(workspace.path(rel).read_bytes()).hexdigest()


def can_read(rel: str) -> bool:
    return Path(rel).suffix.lower() in {".pdf", ".eml", ".md", ".txt"}


def cached(rel: str) -> ReadResult | None:
    data = store.read_json(f"extracted/{sha256(rel)}.read.json")
    return ReadResult.model_validate(data) if data else None


def needs_ocr(rel: str) -> bool:
    if Path(rel).suffix.lower() != ".pdf":
        return False
    doc = pymupdf.open(workspace.path(rel))
    return any(len(p.get_text().strip()) < 30 for p in doc)


def read(rel: str, ocr: bool = True) -> ReadResult:
    """`ocr=False` skips scanned pages (they come back empty) unless already cached."""
    if hit := cached(rel):
        return hit
    p = workspace.path(rel)
    suffix = p.suffix.lower()
    pages: list[PageText] = []
    if suffix == ".pdf":
        doc = pymupdf.open(p)
        for i, page in enumerate(doc, start=1):
            text = page.get_text()
            if len(text.strip()) >= 30:
                pages.append(PageText(page=i, text=text, method="text_layer"))
            elif ocr:
                pages.append(
                    PageText(page=i, text=_ocr(page_png(rel, i, 200)), method="vision_ocr")
                )
            else:
                return ReadResult(path=rel, sha256=sha256(rel), pages=[])
    elif suffix == ".eml":
        pages.append(PageText(page=1, text=_email_text(p), method="native"))
    else:
        pages.append(PageText(page=1, text=p.read_text(), method="native"))
    result = ReadResult(path=rel, sha256=sha256(rel), pages=pages)
    store.write_json(f"extracted/{result.sha256}.read.json", result)
    return result


def _email_text(p: Path) -> str:
    msg = email.message_from_bytes(p.read_bytes(), policy=policy.default)
    body = msg.get_body(preferencelist=("plain",))
    head = "\n".join(f"{h}: {msg[h]}" for h in ("From", "To", "Date", "Subject") if msg[h])
    return f"{head}\n\n{body.get_content() if body else ''}"


def _ocr(png: bytes) -> str:
    from app.llm import get_llm

    model = settings.llm_model_vision
    if not model and settings.llm_provider != "fake":
        raise RuntimeError("LLM_MODEL_VISION is not set: needed to read scanned PDFs.")
    prompt = [
        {
            "role": "user",
            "content": [
                {"text": OCR_PROMPT},
                {"image": {"format": "png", "source": {"bytes": png}}},
            ],
        }
    ]
    return get_llm().complete(prompt, model=model, max_tokens=4096, label="ocr").text


@lru_cache(maxsize=64)
def _png(abs_path: str, mtime: float, page: int, dpi: int) -> bytes:
    doc = pymupdf.open(abs_path)
    return doc[page - 1].get_pixmap(dpi=dpi).tobytes("png")


def page_png(rel: str, page: int = 1, dpi: int = 110) -> bytes:
    p = workspace.path(rel)
    return _png(str(p), p.stat().st_mtime, page, dpi)


def page_count(rel: str) -> int | None:
    if Path(rel).suffix.lower() != ".pdf":
        return None
    return len(pymupdf.open(workspace.path(rel)))
