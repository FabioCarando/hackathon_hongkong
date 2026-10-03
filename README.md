Repository per Hackaton di domenica 4 ottobre 2026 presso l'Universita' di HK.

`testa che facciamo un bel lavoro`

`Buongiorno, siamo messi`

`ALLOLA?`

`Siamo carichi`

`Il tempo scorre`

## Quickstart

```bash
# once: install uv  →  https://docs.astral.sh/uv/getting-started/installation/
uv sync                                   # creates .venv with Python 3.12 + all deps
cp .env.example .env                      # fill in OPENROUTER_API_KEY
uv run pre-commit install                 # lint + lockfile check on every commit
uv run python scripts/check_env.py        # verify key, credits + which models work
uv run streamlit run streamlit_app.py     # http://localhost:8501
```

No credentials yet? `LLM_PROVIDER=fake uv run streamlit run streamlit_app.py`.

## LLM: any model on OpenRouter

`app/llm/` calls [OpenRouter](https://openrouter.ai) by default: one API key, hundreds of models, so switching model is one line in `.env` (any slug from <https://openrouter.ai/models>):

```bash
LLM_MODEL=openai/gpt-oss-120b                        # or qwen/qwen3-235b-a22b-2507,
LLM_MODEL_FAST=openai/gpt-oss-20b                    #    meta-llama/llama-4-maverick, deepseek/deepseek-chat-v3.1, ...
```

- Cost per call is the **real** amount OpenRouter charged, not an estimate.
- Models differ a lot at tool use and structured output: `check_env.py` tests ping, a tool call and an `extract` for each configured model. Pick models from what passes.
- **Amazon Bedrock is still supported** (`LLM_PROVIDER=bedrock`), but from Hong Kong it was unusable for us (3 Oct): Claude and OpenAI gpt-5.x are geo-blocked, and new AWS accounts start with a daily token quota of ~0. See [`boilerplate.md`](boilerplate.md) section 9.

Full API and options: [`boilerplate.md`](boilerplate.md) section 6.

## Environment rules

- Run everything with `uv run ...`. It syncs `.venv` to `uv.lock` first, so after a pull your env is fixed automatically.
- Never `pip install`. Never hand-edit `uv.lock`.
- Dependencies change only via `uv add <pkg>` / `uv remove <pkg>`, by the env owner, in a tiny PR of its own.
- `uv.lock` merge conflict: `git checkout --theirs uv.lock && uv lock`, then commit.
- Pre-commit hook blocks you in the last hours? `git commit --no-verify` is fine after 19:00.
