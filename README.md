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
uv run python scripts/check_env.py        # verify AWS + Bedrock + model access
uv run streamlit run streamlit_app.py     # http://localhost:8501
```

No credentials yet? `LLM_PROVIDER=fake uv run streamlit run streamlit_app.py`.

## Environment rules

- Run everything with `uv run ...`. It syncs `.venv` to `uv.lock` first, so after a pull your env is fixed automatically.
- Never `pip install`. Never hand-edit `uv.lock`.
- Dependencies change only via `uv add <pkg>` / `uv remove <pkg>`, by the env owner, in a tiny PR of its own.
- `uv.lock` merge conflict: `git checkout --theirs uv.lock && uv lock`, then commit.
- Pre-commit hook blocks you in the last hours? `git commit --no-verify` is fine after 19:00.
