"""Reusable Streamlit pieces. Keep pages thin: layout in pages, look & feel here."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict

import botocore.exceptions
import pandas as pd
import streamlit as st

from app.config import settings
from app.llm import AgentResult, AgentStep, Result, telemetry


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
        mode = "FAKE" if settings.llm_provider == "fake" else "bedrock"
        st.caption(f"`{settings.llm_model}` · {settings.aws_region} · {mode}")
        if settings.llm_cache == "on":
            st.caption(":material/save: disk cache on")


def calls_dataframe() -> pd.DataFrame:
    return pd.DataFrame([asdict(c) for c in telemetry.CALLS])


@contextmanager
def llm_errors() -> Iterator[None]:
    """Turn the usual AWS/Bedrock failures into a readable message instead of a traceback."""
    try:
        yield
    except botocore.exceptions.NoCredentialsError:
        st.error("No AWS credentials. Fill `.env` (see `.env.example`) or set `AWS_PROFILE`.")
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            st.error(f"Access denied for `{settings.llm_model}`. Run `scripts/check_env.py`. {e}")
        elif "unsupported countries" in str(e):
            st.error(
                f"`{settings.llm_model}`'s provider is geo-blocked for us. Pick another model."
            )
        elif code in ("ResourceNotFoundException", "ValidationException"):
            st.error(f"Model rejected the request: `{settings.llm_model}`. Run `check_env`. {e}")
        elif code in ("ThrottlingException", "ServiceQuotaExceededException"):
            if "per day" in str(e):
                st.error(
                    "Daily Bedrock token quota used up. Switch model or turn on `LLM_CACHE=on`."
                )
            else:
                st.error("Throttled by Bedrock. Wait a few seconds, use `fast`, or `LLM_CACHE=on`.")
        else:
            st.error(f"AWS error: {e}")
    except botocore.exceptions.TokenRetrievalError as e:
        st.error(f"AWS error: {e}")
    except (botocore.exceptions.EndpointConnectionError, botocore.exceptions.ReadTimeoutError):
        st.error("Network error. Check wifi or switch on `LLM_CACHE=on` to replay cached answers.")
    except RuntimeError as e:
        if "credential" not in str(e).lower():
            raise
        st.error("No AWS credentials. Fill `.env` (see `.env.example`) or set `AWS_PROFILE`.")
