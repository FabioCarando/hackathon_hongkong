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
cp .env.example .env                      # fill in AWS credentials
uv run pre-commit install                 # lint + lockfile check on every commit
uv run python scripts/check_env.py        # verify AWS + Bedrock + which models work
uv run streamlit run streamlit_app.py     # http://localhost:8501
```

No credentials yet? `LLM_PROVIDER=fake uv run streamlit run streamlit_app.py`.

## LLM: any model on Bedrock

`app/llm/` calls Amazon Bedrock through the **Converse API**, which is the same for every model, so switching model is one line in `.env`:

```bash
LLM_MODEL=us.amazon.nova-pro-v1:0                    # or us.meta.llama4-maverick-17b-instruct-v1:0,
LLM_MODEL_FAST=us.amazon.nova-lite-v1:0              #    openai.gpt-oss-120b-1:0, us.deepseek.r1-v1:0, ...
```

Things we learned testing from Hong Kong (3 Oct):

- **Claude and OpenAI gpt-5.x are geo-blocked** on Bedrock ("not allowed from unsupported countries"). Nova, Llama, gpt-oss, DeepSeek, Mistral and Qwen are not.
- **New AWS accounts start with a daily token quota of ~0**, so every call fails with `ThrottlingException: Too many tokens per day`. Use the organisers' account or request an increase in Service Quotas.
- Models differ a lot at tool use and structured output: `check_env.py` tests ping, a tool call and an `extract` for each configured model. Pick models from what passes.

Full API and options: [`boilerplate.md`](boilerplate.md) section 6.

## Environment rules

- Run everything with `uv run ...`. It syncs `.venv` to `uv.lock` first, so after a pull your env is fixed automatically.
- Never `pip install`. Never hand-edit `uv.lock`.
- Dependencies change only via `uv add <pkg>` / `uv remove <pkg>`, by the env owner, in a tiny PR of its own.
- `uv.lock` merge conflict: `git checkout --theirs uv.lock && uv lock`, then commit.
- Pre-commit hook blocks you in the last hours? `git commit --no-verify` is fine after 19:00.
