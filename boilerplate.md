# Boilerplate guide

This guide covers the scaffolding we prepared before 4 Oct, so that on the day we spend our time on product code instead of setup. **Read it once before Sunday.** It covers how to run the project, how to call the LLM, how to keep the shared environment from breaking, and what to do at kickoff.

Everything here is idea-agnostic: it works whatever we end up building.

---

## 1. What you get

| Piece | Where | What it gives you |
|---|---|---|
| Reproducible environment | `pyproject.toml`, `uv.lock`, `.python-version` | The same Python 3.12 and package versions on every laptop, set up with one command |
| LLM wrapper | `app/llm/` | One small API to call any text model on Amazon Bedrock (Nova, Llama, Mistral, DeepSeek, Qwen, gpt-oss...): plain text, streaming, structured (pydantic) output and tool-using agents |
| Cost and latency tracking | `app/llm/telemetry.py`, `app/llm/pricing.py` | Every call records latency, tokens and estimated USD cost, both in memory and in `logs/llm_calls.jsonl` |
| Simulated model | `app/llm/fake.py` | Develop and test with no AWS account, no network and no cost |
| Disk cache | built into the wrapper | A repeated request is answered from disk: free, instant, and it works if the venue wifi dies |
| Environment check | `scripts/check_env.py` | At kickoff, tells us in one minute which AWS account, region and models we can actually use, and which of them handle tool use and structured output |
| Quality gates | `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `tests/` | Auto-formatting, a lockfile check and smoke tests, so `main` doesn't break |
| Demo UI | `streamlit_app.py`, `app/ui/` | A reference Streamlit app that shows the boilerplate working. It isn't meant to be our product |

---

## 2. Setup

### First time (about 2 minutes)

1. Install **uv**: <https://docs.astral.sh/uv/getting-started/installation/>. It works on macOS, Linux and Windows.
2. From the repo root, run:

```bash
uv sync                              # creates .venv with Python 3.12 and every dependency
cp .env.example .env                 # then fill it in (see section 5)
uv run pre-commit install            # enables the commit hooks
```

You don't need to install Python yourself, because uv downloads 3.12 if it's missing. You never need to activate the venv either.

### Every day

```bash
uv run streamlit run streamlit_app.py      # demo UI on http://localhost:8501
uv run pytest -q                           # tests (offline, ~1s)
uv run python scripts/check_env.py         # check AWS + Bedrock access
uv run python some_script.py               # run any script inside the env
```

**No AWS credentials yet?** Put `LLM_PROVIDER=fake` in `.env`, or prefix any command with it:

```bash
LLM_PROVIDER=fake uv run streamlit run streamlit_app.py
```

---

## 3. Repo layout and ownership

```
app/
  config.py          settings, read from .env / environment variables
  llm/               Bedrock LLM wrapper (client, reply, fake simulator, pricing, telemetry)
  core/              ← product / domain logic goes here
  data/              ← data loading, simulators, datasets go here
  ui/                Streamlit components and pages
scripts/check_env.py kickoff connectivity check
tests/               offline smoke tests
ideas/               idea notes and competition criteria (not code)
streamlit_app.py     Streamlit entry point
```

**Ownership on the day:** each person owns separate folders, so merge conflicts mostly disappear.

| Owner | Area |
|---|---|
| A | `app/llm/`, prompts and agents, AWS, **the environment** (`pyproject.toml` / `uv.lock`) |
| B | `app/core/`, `app/data/`: domain logic, data, simulators |
| C | UI and demo flow, pitch, backup video |

**Contracts first:** at about 10:30 we agree the pydantic models passed between data, core and UI, then build in parallel against them.

---

## 4. Environment rules (read this part carefully)

Most environments break because `pyproject.toml`, `uv.lock` and someone's local `.venv` stop matching. These rules prevent that.

1. **Always run things with `uv run ...`.** Before running, it syncs `.venv` to `uv.lock`. After a `git pull` that changed dependencies, your environment updates itself, and there is nothing to remember.
2. **Never `pip install`.** Anything installed that way is invisible to everyone else and gets wiped on the next sync.
3. **Only the environment owner adds or removes dependencies**, with `uv add <pkg>` / `uv remove <pkg>`, in a small PR on its own. Ask them; don't edit `pyproject.toml` yourself.
4. **Most of what we might need is already installed:** `boto3`, `streamlit`, `pydantic`, `pandas`, `numpy`, `plotly`, `scikit-learn`, `networkx`, `faker`, `pyyaml`, `python-dotenv`. Check before asking for something new.
5. **Never edit `uv.lock` by hand.** If it has a merge conflict, run:
   ```bash
   git checkout --theirs uv.lock && uv lock
   ```
   then commit the result.
6. **Python is pinned to 3.12**, so different machines can't drift apart.

These are enforced automatically:
- **Pre-commit hook:** `uv lock --check` blocks a commit where `pyproject.toml` and `uv.lock` don't match.
- **CI:** `uv sync --locked` fails the PR if they don't match, so a broken pair never reaches `main`.

---

## 5. Configuration (`.env`)

Everything is configured through environment variables. Copy `.env.example` to `.env` and fill it in. **Never commit `.env`**; it's already in `.gitignore`.

| Variable | Default | Meaning |
|---|---|---|
| `AWS_PROFILE` | – | Use a named profile from `~/.aws/config` (SSO or keys) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | – | Or paste the temporary credentials the organisers give us |
| `AWS_REGION` | `us-west-2` | Bedrock region. Use whatever the organisers' account is set up for |
| `LLM_PROVIDER` | `bedrock` | `bedrock` = real calls; `fake` = simulated model (section 8) |
| `LLM_MODEL` | `us.amazon.nova-pro-v1:0` | Main model. Any Bedrock model or inference-profile ID; switching model is just this line |
| `LLM_MODEL_FAST` | `us.amazon.nova-lite-v1:0` | Cheaper and faster model, used when you pass `fast=True` |
| `LLM_MAX_TOKENS` | `4096` | Default output cap per call. Bedrock reserves this much quota per request, so keep it modest. Automatically clamped to the model's limit |
| `LLM_CACHE` | `off` | `on` = read-through disk cache (section 7) |
| `LLM_CACHE_DIR` | `.llm_cache` | Where cached answers live. Point it at a committed folder to share a demo cache with the team |
| `FAKE_LATENCY` | `1` | Fake provider only: `0` = instant, `1` = roughly real model speed |

In code, read settings from `app.config.settings` (for example `settings.llm_model`). Never call `os.getenv` directly.

---

## 6. Calling the LLM: the wrapper

All product code talks to the model through one object. Under the hood it uses Bedrock's **Converse API**, which is the same for every model on Bedrock, so changing `LLM_MODEL` is all it takes to switch provider:

```python
from app.llm import get_llm

llm = get_llm()
```

There are four methods. Each one takes a prompt, which is either a string or a list of messages (`[{"role": "user", "content": "..."}, ...]`; content can be a string or a list of Converse content blocks) for multi-turn conversations, plus these options:

| Option | Meaning |
|---|---|
| `system="..."` | System prompt |
| `fast=True` | Use `LLM_MODEL_FAST` instead of `LLM_MODEL` |
| `model="..."` | Override the model ID for this call |
| `max_tokens=...` | Override the output cap (not on `extract`) |
| `effort="low" \| "medium" \| "high"` | How hard the model thinks, for reasoning models that support it (currently mapped for gpt-oss and Nova 2). Ignored on other models. Not on `extract` |
| `label="triage"` | Tag shown in the call log, so you can tell calls apart |

### 6.1 `complete`: plain text

```python
r = llm.complete("Summarise this client's activity: ...", system="You are an AML analyst.")
r.text          # the answer
r.stats         # latency_ms, input_tokens, output_tokens, cost_usd, model, cached, ...
r.reply         # the raw Reply (Converse content blocks, stop_reason, usage)
```

### 6.2 `extract`: structured output (use this most)

Define a pydantic model, and the model's answer comes back already validated into it. This is how to get reliable data out of the LLM, rather than parsing free text.

```python
from typing import Literal
from pydantic import BaseModel, Field

class Triage(BaseModel):
    decision: Literal["escalate", "close"]
    reasons: list[str] = Field(description="Specific facts that drove the decision")
    confidence: float = Field(ge=0, le=1)

triage, r = llm.extract(f"Triage this alert:\n{alert_json}", Triage, label="triage")
triage.decision      # "escalate"
r.stats.cost_usd     # 0.0021
```

`Field(description=...)` text is sent to the model, so use it to explain what each field should contain.

How it works: the schema is sent as a tool the model is forced to call. Models that can't force a specific tool fall back to "call any tool", then to "reply with JSON". The mode that works is remembered per model, and if the answer fails validation the error is sent back for one retry. Smaller models are much less reliable here, so check `extract` passes in `check_env` before relying on a model.

### 6.3 `stream`: text that appears as it's generated

```python
s = llm.stream("Explain this alert to a compliance officer.")
for chunk in s:            # or: st.write_stream(s) in Streamlit
    print(chunk, end="")
s.result.stats             # available once the loop has finished
```

### 6.4 `run_agent`: the model using our Python functions as tools

Turn any typed function with a docstring into a tool. **The docstring is what the model reads**, so say what the tool does and what its arguments look like.

```python
from app.llm import tool

@tool(example={"client_id": "C-1002"})          # example args are only used by the fake provider
def get_client(client_id: str) -> dict:
    """Fetch a client's KYC profile by ID (e.g. C-1002)."""
    return db[client_id]

@tool
def get_transactions(client_id: str, days: int = 30) -> list[dict]:
    """List a client's transactions over the last N days."""
    return txns_for(client_id, days)

result = llm.run_agent(
    "Investigate alert A-17 for client C-1002. Escalate or close?",
    tools=[get_client, get_transactions],
    system="You are a careful AML investigator. Use tools; never guess numbers.",
    on_step=lambda step: print(step.kind, step.name, step.data),   # optional live callback
    max_turns=10,
)
result.text         # final answer
result.steps        # every text / tool_call / tool_result, in order (good for an audit trail)
result.calls        # stats for each underlying model call
result.cost_usd     # total cost
result.latency_ms   # total model time
```

How it behaves:
- Tool arguments are validated against the function's type hints before your function runs.
- If a tool raises an exception, the error goes back to the model, which can recover. The app doesn't crash, and the step is marked `is_error=True`.
- Tools can return a `str`, a `dict` / `list` (sent as JSON) or a pydantic model.
- `on_step` fires as each step happens. Use it to show tool calls live on screen, which makes a strong demo moment.
- If you need structured output at the end, run `run_agent` first and then pass `result.text` to `extract`.

### 6.5 Choosing a model

- Pick models from what `check_env` shows passing **ping, tool use and extract**. Non-Claude models vary a lot at tool calling and structured output.
- Use `fast=True` (`LLM_MODEL_FAST`) for simple, high-volume or latency-sensitive steps: classification, short extraction, pings.
- You can mix models: pass `model="..."` per call, for example a strong model for `run_agent` and a cheap one for bulk `extract`.

---

## 7. Cost, latency and the disk cache

### Telemetry

Every call through the wrapper is logged automatically:
- **In memory:** `app.llm.telemetry.CALLS` (a list of `CallStats`) and `telemetry.totals()` for aggregates.
- **On disk:** `logs/llm_calls.jsonl`, one JSON line per call (gitignored).

Each record holds the model, label, input/output tokens, cache tokens, latency in ms, estimated cost in USD, whether the answer came from the cache, and the stop reason.

**Why it matters for the pitch:** judges score industry impact. A line like "triaging one alert costs $0.002 and takes 3 seconds, versus 40 minutes of analyst time" is far more convincing with real numbers, and the call log gives us those numbers for free.

Costs are **estimates** based on Bedrock on-demand prices (US regions) in `app/llm/pricing.py`. Other regions and newer models can differ. Add a model to `PRICES` there if it shows `n/a`.

### Disk cache (`LLM_CACHE=on`)

- Every request is hashed (model, prompt, system, tools, schema). If an identical request was made before, the stored answer comes back instantly and costs nothing.
- If anything in the request changes, the cache misses and a real call is made and stored.
- **Demo insurance:** run the full demo flow once with the cache on, before going on stage. The demo then replays identically with no network. To share it, set `LLM_CACHE_DIR=demo_cache` and commit that folder.
- It also helps while iterating on the UI: you aren't paying for the same call over and over.
- Turn it off when you *want* fresh answers, for example while tuning a prompt and comparing outputs.

---

## 8. Working without AWS: the fake provider

`LLM_PROVIDER=fake` swaps Bedrock for a local simulator (`app/llm/fake.py`). It's meant for UI work, offline development, tests, or when Bedrock is slow or throttled.

| Method | What the simulator does |
|---|---|
| `complete` / `stream` | Returns a plausible markdown answer that mentions your prompt, and streams it gradually |
| `extract` | Returns random **valid** values for your pydantic schema (Literal choices, numbers between 0 and 1, lists, nested models) |
| `run_agent` | Turn 1: really calls **every** tool you passed, with its `example` args (or random args if there's no example). Turn 2: writes a conclusion quoting the tool results |
| Stats | Realistic latency (controlled by `FAKE_LATENCY`), token counts estimated from text length, and estimated cost |

Outputs are deterministic, so the same prompt always gives the same answer. That keeps tests and screenshots stable.

Add `example={...}` to your `@tool`s so agent flows exercise your real tool code even offline.

Fake answers are obviously fake (they say "Simulated answer"), so you can't mistake them for real results.

---

## 9. Kickoff checklist (Sunday morning)

1. Put the organisers' AWS credentials in `.env`, either a profile or the three key variables, plus the region.
2. Run:
   ```bash
   uv run python scripts/check_env.py
   ```
   It checks, in order:
   - **AWS identity:** whether the credentials work.
   - **Text models and inference profiles:** which model IDs this account can use in this region.
   - **For `LLM_MODEL` and `LLM_MODEL_FAST`: a ping, a tool call and an `extract`:** whether real calls work end to end, and whether the model handles tools and structured output.
3. If something fails:

| Symptom | Fix |
|---|---|
| `NoCredentialsError` / "Could not resolve AWS credentials" | `.env` isn't filled in, or the profile name is wrong |
| `ValidationException` / invalid model ID | Choose an ID from the lists the script prints, and set `LLM_MODEL` / `LLM_MODEL_FAST` |
| "on-demand throughput isn't supported" | Use the inference profile ID (for example `us.amazon.nova-pro-v1:0`) in place of the bare model ID |
| Tool use or extract fails for a model | Use a different model for that job (`model=...` on the call) |
| "Access to Anthropic/OpenAI models is not allowed from unsupported countries" | Bedrock geo-blocks these providers for us; use Nova, Llama, gpt-oss, DeepSeek, Mistral or Qwen |
| `AccessDeniedException` | The account lacks Bedrock permissions or model access, so ask the organisers |
| `ThrottlingException` ("Too many tokens per day" = daily quota exhausted or 0) | Use `fast=True` for bulk calls, turn on the cache, and ask organisers about quotas |

The script exits with code 0 only when everything passes.

---

## 10. Quality gates

| Gate | When | What it does |
|---|---|---|
| Pre-commit hook | every `git commit` | Checks `uv.lock` matches `pyproject.toml`, runs `ruff check --fix` (real bugs such as undefined names and unused imports, plus import order) and `ruff format` (consistent formatting, which avoids pointless merge conflicts) |
| CI (GitHub Actions) | every push to `main` and every PR | `uv sync --locked`, `ruff check`, `pytest` with the fake provider |
| Tests | `uv run pytest -q` | Offline smoke tests of every wrapper feature, about 1 second |

- If the hook auto-fixes a file, the commit stops. Run `git add` again and re-commit.
- In the last hours, `git commit --no-verify` is acceptable after 19:00.
- Ruff deliberately checks only for real bugs, not style, and the formatter handles style. Formatting doesn't block CI.

### Team git workflow

- Use short branches named `name/feature`, open a PR, and **self-merge once CI is green**. No review is needed before 17:00.
- Merge at least every 1–2 hours, and pull often.
- **`main` must always run.** If you break it, fixing it comes before anything else.

---

## 11. The demo UI (reference only)

`streamlit_app.py` and `app/ui/` exist to **show the boilerplate working**. We probably won't use it as our product UI, but it's handy for seeing what each feature does and for copying patterns.

```bash
LLM_PROVIDER=fake uv run streamlit run streamlit_app.py
```

| Page | Demonstrates |
|---|---|
| Overview | Settings in use, plus a one-click "Ping Bedrock" connection check |
| LLM playground | `stream` (text appearing live) and `extract` (pydantic output shown as a risk badge plus JSON) |
| Agent demo | `run_agent` with two toy tools, with each tool call and result shown live |
| Call log | Every call this session: a latency chart, total cost, and the full table |
| Sidebar (all pages) | Running totals: calls, spend, average latency, tokens |

Patterns worth reusing if we do build a Streamlit UI:
- **`app/ui/components.py`:**
  - `stats_row(result)` shows latency, tokens, cost and model under any output.
  - `render_step(step)` draws agent steps.
  - `with llm_errors():` turns AWS/Bedrock exceptions into readable messages instead of tracebacks. **Wrap every LLM call in a page with this.**
- **Adding a page:** create `app/ui/views/my_page.py`, then add `st.Page("app/ui/views/my_page.py", title=..., icon=...)` to the navigation in `streamlit_app.py`.
- **Theme:** `.streamlit/config.toml` sets a dark theme. Saving a file hot-reloads the page.

---

## 12. Limitations and things to verify

- **No successful live call yet.** The Converse code path is tested offline (request shapes validated against the boto3 schema, Bedrock stubbed in `tests/test_smoke.py`), and a live run on a personal account got as far as Bedrock's quota check. `check_env.py` confirms it on the day.
- **Claude and OpenAI gpt-5.x are geo-blocked for us on Bedrock**; a new personal AWS account also has ~0 daily token quota for every model (section 9).
- **Costs are estimates** at Bedrock US list prices (section 7).
- **`effort` is mapped only for gpt-oss and Nova 2**, and those field names are unverified. Other models ignore it.
- **Telemetry is per process.** Restarting the app resets the in-memory totals, but the JSONL log keeps everything.
- **`extract` doesn't take `effort` or `max_tokens` overrides.** Use `complete` plus your own parsing if you really need them.
- **The cache matches exact requests only.** Changing one character in a prompt is a miss, which is by design.

---

## 13. Quick reference

```python
from app.config import settings
from app.llm import get_llm, tool

llm = get_llm()
llm.complete(prompt, system=..., fast=..., effort=..., label=...)          -> Result(text, stats, reply)
llm.extract(prompt, MyModel, system=..., fast=..., label=...)             -> (MyModel, Result)
llm.stream(prompt, ...)                                                   -> iterable of str; .result after
llm.run_agent(prompt, tools=[...], system=..., on_step=..., max_turns=10) -> AgentResult(text, steps, calls)

@tool                       # or @tool(example={...})
def my_tool(arg: str) -> dict:
    """What it does. The model reads this."""
```

```bash
uv sync                                          # set up / repair the environment
uv run streamlit run streamlit_app.py            # demo UI
uv run pytest -q                                 # tests
uv run python scripts/check_env.py               # AWS + Bedrock check
uv add <pkg>                                     # environment owner only
git checkout --theirs uv.lock && uv lock         # resolve a lockfile conflict
```
