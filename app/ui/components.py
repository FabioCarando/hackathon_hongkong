"""Reusable Streamlit pieces. Keep pages thin: layout in pages, look & feel here."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict

import openai
import pandas as pd
import streamlit as st

from app.config import settings
from app.llm import AgentResult, AgentStep, Result, telemetry

PROVIDER_NAMES = {"openrouter": "OpenRouter", "bedrock": "Amazon Bedrock", "fake": "Fake"}


def header(title: str, caption: str = "") -> None:
    st.title(title)
    if caption:
        st.caption(caption)


def fmt_cost(usd: float | None) -> str:
    if usd is None:
        return "n/a"
    return f"${usd:.4f}" if usd < 1 else f"${usd:.2f}"


def stats_row(r: Result | AgentResult) -> None:
    """Latency / tokens / cost under any LLM output. Judges like seeing unit economics."""
    if isinstance(r, AgentResult):
        latency, cost = r.latency_ms, r.cost_usd
        tokens = sum(c.input_tokens + c.output_tokens for c in r.calls)
        extra = f"{len(r.calls)} calls"
    else:
        s = r.stats
        latency, cost = s.latency_ms, s.cost_usd
        tokens = s.input_tokens + s.output_tokens
        extra = "cached" if s.cached else s.model
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latency", f"{latency / 1000:.2f}s", border=True)
    c2.metric("Tokens", f"{tokens:,}", border=True)
    c3.metric("Cost", fmt_cost(cost), border=True)
    c4.metric("Model", extra, border=True)


def render_step(step: AgentStep) -> None:
    if step.kind == "tool_call":
        st.markdown(f":material/build: **{step.name}**")
        st.json(step.data, expanded=False)
    elif step.kind == "tool_result":
        icon = ":material/error:" if step.is_error else ":material/check_circle:"
        with st.expander(f"{icon} result of `{step.name}`"):
            st.code(str(step.data)[:4000], language="json")
    elif step.kind == "text":
        st.markdown(step.data)


def sidebar() -> None:
    with st.sidebar:
        t = telemetry.totals()
        st.subheader("LLM usage")
        c1, c2 = st.columns(2)
        c1.metric("Calls", t["calls"])
        c2.metric("Spend", fmt_cost(t["cost_usd"]))
        c1.metric("Avg latency", f"{t['avg_latency_ms'] / 1000:.1f}s")
        c2.metric("Tokens", f"{(t['input_tokens'] + t['output_tokens']) / 1000:.1f}k")
        if st.button("Reset counters", width="stretch"):
            telemetry.reset()
            st.rerun()
        where = [settings.aws_region] if settings.llm_provider == "bedrock" else []
        provider = PROVIDER_NAMES[settings.llm_provider]
        st.caption(" · ".join([f"`{settings.llm_model}`", *where, provider]))
        if settings.llm_cache == "on":
            st.caption(":material/save: disk cache on")


def calls_dataframe() -> pd.DataFrame:
    return pd.DataFrame([asdict(c) for c in telemetry.CALLS])


def _openrouter_error(e: openai.OpenAIError) -> str:
    model = settings.llm_model
    if isinstance(e, openai.APITimeoutError):
        return (
            "OpenRouter timed out. Retry, use `fast`, or `LLM_CACHE=on` to replay cached answers."
        )
    if isinstance(e, openai.APIConnectionError):
        return "Network error. Check wifi or switch on `LLM_CACHE=on` to replay cached answers."
    if not isinstance(e, openai.APIStatusError):
        return f"OpenRouter error: {e}"
    code = e.status_code
    if code == 401:
        return "OpenRouter rejected the API key. Check `OPENROUTER_API_KEY` in `.env`."
    if code == 402:
        return (
            "Out of OpenRouter credits (or `LLM_MAX_TOKENS` needs more than is left). Top up at "
            "https://openrouter.ai/settings/credits, lower `LLM_MAX_TOKENS`, or `LLM_CACHE=on`."
        )
    if code == 429:
        return "Rate limited by OpenRouter. Wait a few seconds, use `fast`, or `LLM_CACHE=on`."
    if code == 404 or "no endpoints" in str(e).lower() or "not a valid model" in str(e).lower():
        return (
            f"No OpenRouter provider can serve `{model}` for this request: the slug is wrong, or "
            f"no provider supports the features asked for (e.g. tools). Run `check_env`. {e}"
        )
    if code in (502, 503):
        return f"`{model}` is down upstream right now. Retry or pick another model. {e}"
    return f"OpenRouter error {code}: {e}"


def _bedrock_error(e: Exception) -> str | None:
    import botocore.exceptions as be  # lazy: boto3 is only needed for the Bedrock provider

    if isinstance(e, be.NoCredentialsError):
        return "No AWS credentials. Fill `.env` (see `.env.example`) or set `AWS_PROFILE`."
    if isinstance(e, be.ClientError):
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            return f"Access denied for `{settings.llm_model}`. Run `scripts/check_env.py`. {e}"
        if "unsupported countries" in str(e):
            return f"`{settings.llm_model}`'s provider is geo-blocked for us. Pick another model."
        if code in ("ResourceNotFoundException", "ValidationException"):
            return f"Model rejected the request: `{settings.llm_model}`. Run `check_env`. {e}"
        if code in ("ThrottlingException", "ServiceQuotaExceededException"):
            if "per day" in str(e):
                return "Daily Bedrock token quota used up. Switch model or turn on `LLM_CACHE=on`."
            return "Throttled by Bedrock. Wait a few seconds, use `fast`, or `LLM_CACHE=on`."
        return f"AWS error: {e}"
    if isinstance(e, be.TokenRetrievalError):
        return f"AWS error: {e}"
    if isinstance(e, (be.EndpointConnectionError, be.ReadTimeoutError)):
        return "Network error. Check wifi or switch on `LLM_CACHE=on` to replay cached answers."
    if isinstance(e, RuntimeError) and "credential" in str(e).lower():
        return "No AWS credentials. Fill `.env` (see `.env.example`) or set `AWS_PROFILE`."
    return None


@contextmanager
def llm_errors() -> Iterator[None]:
    """Turn the usual provider failures into a readable message instead of a traceback."""
    try:
        yield
    except openai.OpenAIError as e:
        st.error(_openrouter_error(e))
    except Exception as e:
        if isinstance(e, RuntimeError) and "openrouter" in str(e).lower():  # key unset, no answer
            st.error(str(e))
        elif settings.llm_provider == "bedrock" and (msg := _bedrock_error(e)):
            st.error(msg)
        else:
            raise
