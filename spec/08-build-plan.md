# 08 · Build plan

Ordered so that each step ends with something runnable. Do the steps in order. Don't start a P1 step until every step marked P0 is done and `scripts/eval.py` passes its P0 rows.

## Repo rules (from `boilerplate.md`)

- Run everything with `uv run ...`. Never `pip install`. Never hand-edit `uv.lock`.
- New dependencies only via `uv add` by the env owner, in a small PR. Needed now: `uv add openpyxl pymupdf`.
- LLM calls only through `app.llm.get_llm()`. Settings only through `app.config.settings`. Wrap LLM calls in UI pages with `llm_errors()`.
- Ruff + format via pre-commit. Tests offline with `LLM_PROVIDER=fake`. `main` must always run.
- Never write to `workspace/` from the app. Use the runtime copy.

## Steps

| # | Step | Files | Done when | Label |
|---|---|---|---|---|
| 0 | Add deps `openpyxl`, `pymupdf`. Add `runtime/` to `.gitignore`. Add new settings + `.env.example` entries | `pyproject.toml`, `uv.lock`, `.gitignore`, `app/config.py`, `.env.example` | `uv run python -c "import openpyxl, pymupdf"` works | P0 |
| 1 | Pydantic models | `app/core/models.py` | Imports cleanly; matches `03` | P0 |
| 2 | Runtime workspace + git wrapper + JSON store | `app/data/workspace.py`, `app/data/store.py` | `reset()` copies the seed; `git log` on the runtime copy shows 10 commits; `status` lists the untracked demo files | P0 |
| 3 | Sheet IO | `app/data/sheets.py` | Read Register/Forecast to DataFrames with cell refs; write cells + append rows keeping formulas; round-trip test | P0 |
| 4 | Indexer | `app/core/indexer.py` | `index.json` lists every file with kind/status; 9 new files flagged (6 inbox documents, lease, 2 emails) | P0 |
| 5 | Image support in LLM wrapper + vision setting; fake OCR | `app/llm/openrouter.py`, `app/llm/fake.py`, `app/config.py` | A test sends an image block through the mocked OpenRouter layer as `image_url`; text-only paths unchanged; existing tests pass | P0 |
| 6 | Reader (text layer → vision OCR fallback, cache) | `app/core/reader.py` | F3 acceptance passes with the real vision model; the second run makes 0 LLM calls | P0 |
| 7 | Extractor + code validation + supplier matching | `app/core/extractor.py` | F4 acceptance (≥ 95% fields) on the 6 inbox documents; S04 lease → rent 98,800, +3%, from 2027-01-01, p.3 | P0 |
| 8 | Expectations seeding | `app/core/expectations.py`, `scripts/seed_brain.py` | F5 acceptance | P0 |
| 9 | Checks | `app/core/checks.py`, `tests/test_checks.py` | F6 acceptance as unit tests on hand-built `InvoiceData` (no LLM) | P0 |
| 10 | Versioning + change sets | `app/core/versioning.py`, `app/core/changes.py`, `tests/test_versioning.py` | Apply a change set on a temp copy → xlsx updated, `sources.json` appended, commit with reason; `history()` returns old + new entries for C5 | P0 |
| 11 | Intake orchestration + questions + decisions | `app/core/intake.py`, `app/core/decisions.py` | Script run: 3 clean → proposed change sets; 2 held → questions; reject both → HELD rows + decisions + commits; lease → forecast change set (F10) | P0 |
| 12 | Search | `app/core/search.py` | F9 acceptance | P0 |
| 13 | Ask agent | `app/core/ask.py` | F11 P0 acceptance | P0 |
| 14 | Eval script | `scripts/eval.py` | Prints the metrics table from `06`; all P0 rows pass | P0 |
| 15 | UI: sidebar, Inbox, Files, History, Memory, Ask | `app/ui/views/*.py`, `streamlit_app.py` | The demo script in `06` runs start to finish by clicking | P0 |
| 16 | Rehearse with the real model, warm `LLM_CACHE`, **record backup video** | — | Video saved | P0 (by 19:00) |
| 17 | DOMAIN/UNKNOWN/AMOUNT/CONTRACT checks fully; citation validator; deadlines banner; Excel cell comments; editable fields; COMPANY.md update on lease | various | F6/F11/F12/F13 P1 acceptance | P1 |
| 18 | Bank reconciliation, audit pack, learn-then-pass invoice | various | F14–F16 | P2 |

## Parallel split (3 people)

| Owner | Steps |
|---|---|
| A: LLM + pipeline | 0, 5, 6, 7, 13 |
| B: memory + history | 1, 2, 3, 4, 8, 9, 10, 11, 12, 14 |
| C: UI + pitch | 15 (start on step 1 models with fake data), 16, slides from `07` |

Agree on `models.py` (step 1) first, by about 10:30. Then everyone builds against it.

## Definition of done (P0)

- [ ] `uv run pytest -q` passes offline.
- [ ] `uv run python scripts/eval.py` passes every P0 metric in `06` with the real models.
- [ ] Demo script in `06` runs in the UI end to end, twice in a row, with a reset in between.
- [ ] `workspace/` unchanged in the outer repo after the demo (`git status` clean).
- [ ] Backup video recorded.

## Timeline (4 Oct)

| Time | Goal |
|---|---|
| 09:30–10:30 | Kickoff, confirm criteria, `check_env.py`, **pick the vision model on the Chinese scan**, freeze models.py |
| 10:30–14:00 | Steps 0–12 in parallel |
| 14:00–17:00 | Steps 13–15. **Demo runs end to end by 17:00** |
| 17:00–19:00 | Step 16 (video), then P1 |
| 19:00–21:00 | Pitch rehearsal ×3, submission |

## Risks

| Risk | Mitigation |
|---|---|
| Vision OCR poor on the Chinese scan | Test first at kickoff; try 2–3 models; the OCR cache freezes a good result; editable fields as a fallback |
| Model tool-calling flaky for Ask | Cap turns at 8; pre-warmed cache; the suggested questions are the rehearsed ones |
| openpyxl drops formulas/formatting | Load without `data_only`; append rows by copying the previous row's style and formula pattern; round-trip test in step 3 |
| Runtime copy breaks the workspace git (`core.worktree`) | `reset()` rewrites `core.worktree`; always pass `--git-dir` and `--work-tree` explicitly |
| Scope creep | P0 list only until 17:00; reports are explicitly out |
| Venue wifi | Cache + backup video |
