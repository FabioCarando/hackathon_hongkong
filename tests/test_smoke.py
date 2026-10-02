"""Runs with LLM_PROVIDER=fake: no network, no AWS credentials needed."""

from typing import Literal

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm import LLM, tool
from app.llm.pricing import base_model, cost_usd


def fake_settings(tmp_path, **kw) -> Settings:
    base = dict(
        llm_provider="fake",
        llm_cache="off",
        fake_latency=0,
        llm_log_path=str(tmp_path / "log.jsonl"),
    )
    return Settings(**(base | kw))


@pytest.fixture
def llm(tmp_path) -> LLM:
    return LLM(fake_settings(tmp_path))


def test_complete(llm):
    r = llm.complete("hello")
    assert "hello" in r.text
    assert r.stats.cost_usd is not None and r.stats.cost_usd > 0


def test_stream(llm):
    s = llm.stream("hello stream")
    assert "hello stream" in "".join(s)
    assert s.result is not None


class Verdict(BaseModel):
    decision: Literal["escalate", "close"]
    reasons: list[str]
    confidence: float
    note: str | None = None


def test_extract_validates_against_schema(llm):
    obj, _ = llm.extract("classify", Verdict)
    assert obj.decision in ("escalate", "close")
    assert obj.reasons and 0 <= obj.confidence <= 1


def test_agent_calls_tools_then_answers(llm):
    calls = []

    @tool(example={"client_id": "C1"})
    def lookup(client_id: str, limit: int = 5) -> dict:
        """Look up a client."""
        calls.append(client_id)
        return {"id": client_id}

    @tool
    def broken(x: int) -> int:
        """Always fails."""
        raise ValueError("boom")

    assert lookup.input_schema["required"] == ["client_id"]
    result = llm.run_agent("go", tools=[lookup, broken])
    kinds = [s.kind for s in result.steps]
    assert calls == ["C1"]
    assert kinds.count("tool_call") == 2
    assert any(s.is_error for s in result.steps if s.kind == "tool_result")
    assert len(result.calls) == 2 and "C1" in result.text


def test_cache_roundtrip(tmp_path):
    llm = LLM(fake_settings(tmp_path, llm_cache="on", llm_cache_dir=str(tmp_path / "c")))
    first = llm.complete("same")
    second = llm.complete("same")
    assert second.stats.cached and second.text == first.text


def test_pricing():
    assert base_model("global.anthropic.claude-opus-5-v1:0") == "claude-opus-5"
    assert base_model("anthropic.claude-haiku-4-5-20251001-v1:0") == "claude-haiku-4-5"
    assert cost_usd("anthropic.claude-sonnet-5", 1_000_000, 0) == 2.0
    assert cost_usd("unknown-model", 1, 1) is None
