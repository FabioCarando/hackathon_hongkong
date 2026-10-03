"""Runs with LLM_PROVIDER=fake: no network, no AWS credentials needed."""

import json
from typing import Literal

import pytest
from botocore.exceptions import ClientError
from botocore.stub import ANY
from pydantic import BaseModel

from app.config import Settings
from app.llm import LLM, tool
from app.llm.pricing import base_model, cost_usd


def fake_settings(tmp_path, **kw) -> Settings:
    base = dict(
        llm_provider="fake",
        llm_model="us.amazon.nova-pro-v1:0",  # not whatever the local .env says
        llm_model_fast="us.amazon.nova-lite-v1:0",
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
    assert base_model("us.amazon.nova-pro-v1:0") == "amazon.nova-pro"
    assert (
        base_model("global.anthropic.claude-haiku-4-5-20251001-v1:0")
        == "anthropic.claude-haiku-4-5"
    )
    assert (
        base_model(
            "arn:aws:bedrock:us-west-2:1:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0"
        )
        == "meta.llama4-scout-17b-instruct"
    )
    assert cost_usd("us.amazon.nova-pro-v1:0", 1_000_000, 0) == 0.8
    assert cost_usd("unknown-model", 1, 1) is None


class Party(BaseModel):
    name: str


class Case(BaseModel):
    parties: list[Party]


def test_schema_refs_are_inlined():
    from app.llm.client import _json_schema

    assert "$ref" not in json.dumps(_json_schema(Case))


def test_parse_json_tolerates_fences():
    from app.llm.client import _parse_json

    assert _parse_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}


# --- real Converse code path, with Bedrock stubbed out (requests are validated against boto's schema)


def stubbed(tmp_path):
    import boto3
    from botocore.stub import Stubber

    llm = LLM(fake_settings(tmp_path, llm_provider="bedrock"))
    llm._client = boto3.client(
        "bedrock-runtime", region_name="us-west-2", aws_access_key_id="x", aws_secret_access_key="y"
    )
    return llm, Stubber(llm._client)


def converse_response(content, stop="end_turn"):
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 1},
    }


def test_max_tokens_clamped_to_model_limit(tmp_path):
    llm, stub = stubbed(tmp_path)
    limit_error = "The maximum tokens you requested exceeds the model limit of 10000."
    stub.add_client_error("converse", "ValidationException", limit_error)
    stub.add_response(
        "converse",
        converse_response([{"text": "ok"}]),
        {"modelId": ANY, "messages": ANY, "inferenceConfig": {"maxTokens": 10000}},
    )
    stub.add_response(
        "converse",
        converse_response([{"text": "ok"}]),
        {"modelId": ANY, "messages": ANY, "inferenceConfig": {"maxTokens": 10000}},
    )
    with stub:
        assert llm.complete("hi", max_tokens=20000).text == "ok"
        assert llm.complete("again", max_tokens=20000).text == "ok"  # limit remembered
        stub.assert_no_pending_responses()


def test_extract_falls_back_only_on_tool_errors(tmp_path):
    llm, stub = stubbed(tmp_path)
    stub.add_client_error("converse", "ValidationException", "toolChoice is not supported")
    respond = {"toolUse": {"toolUseId": "t", "name": "respond", "input": {"name": "Ann"}}}
    stub.add_response("converse", converse_response([respond], "tool_use"))
    stub.add_client_error(
        "converse", "ValidationException", "not allowed from unsupported countries"
    )
    with stub:
        obj, _ = llm.extract("who", Party)
        assert obj.name == "Ann" and llm._extract_mode[llm.cfg.llm_model] == "any"
        with pytest.raises(ClientError, match="unsupported countries"):
            llm.extract("who", Party, fast=True)  # not a tool problem: raised, not masked
        stub.assert_no_pending_responses()
