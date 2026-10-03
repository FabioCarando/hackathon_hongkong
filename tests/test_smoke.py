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


# --- OpenRouter adapter, with the HTTP layer mocked (real openai SDK, fake transport)


class FakeOpenRouter:
    """Queue of canned HTTP responses; records each request body sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.bodies: list[dict] = []

    def __call__(self, request):
        import httpx2

        self.bodies.append(json.loads(request.content))
        status, body = self.responses.pop(0)
        if isinstance(body, str):  # SSE stream
            return httpx2.Response(status, text=body, headers={"content-type": "text/event-stream"})
        return httpx2.Response(status, json=body)


def openrouter_llm(tmp_path, *responses) -> tuple[LLM, FakeOpenRouter]:
    import httpx2
    import openai

    server = FakeOpenRouter(*responses)
    llm = LLM(fake_settings(tmp_path, llm_provider="openrouter", llm_model="openai/gpt-oss-120b"))
    llm._client = openai.OpenAI(
        api_key="test",
        base_url="https://openrouter.test/api/v1",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(server)),
    )
    return llm, server


def completion(content=None, tool_calls=None, finish="stop", cost=0.0012):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {"id": id_, "type": "function", "function": {"name": name, "arguments": args}}
            for id_, name, args in tool_calls
        ]
    return 200, {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 40},
            "cost": cost,
        },
    }


def test_openrouter_request_translation():
    from app.llm import openrouter

    respond = {"toolSpec": {"name": "respond", "description": "d", "inputSchema": {"json": {}}}}
    params = {
        "modelId": "openai/gpt-oss-120b",
        "system": [{"text": "Be terse."}, {"text": "JSON only."}],
        "inferenceConfig": {"maxTokens": 99},
        "additionalModelRequestFields": {"reasoning": {"effort": "low"}},
        "toolConfig": {"tools": [respond], "toolChoice": {"tool": {"name": "respond"}}},
        "messages": [
            {"role": "user", "content": [{"text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    {"text": "Looking."},
                    {"toolUse": {"toolUseId": "c1", "name": "respond", "input": {"a": 1}}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"toolResult": {"toolUseId": "c1", "content": [{"text": "bad"}]}},
                    {"text": "again"},
                ],
            },
        ],
    }
    req = openrouter.request(params)
    assert req["model"] == "openai/gpt-oss-120b" and req["max_tokens"] == 99
    assert req["messages"] == [
        {"role": "system", "content": "Be terse.\n\nJSON only."},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "Looking.",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "respond", "arguments": '{"a": 1}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "bad"},
        {"role": "user", "content": "again"},
    ]
    assert req["tools"] == [
        {"type": "function", "function": {"name": "respond", "description": "d", "parameters": {}}}
    ]
    assert req["tool_choice"] == {"type": "function", "function": {"name": "respond"}}
    assert req["extra_body"] == {
        "reasoning": {"effort": "low"},
        "provider": {"require_parameters": True},
    }
    any_choice = {**params["toolConfig"], "toolChoice": {"any": {}}}
    assert openrouter.request({**params, "toolConfig": any_choice})["tool_choice"] == "required"
    plain = openrouter.request({**params, "toolConfig": None, "additionalModelRequestFields": {}})
    assert "tools" not in plain and "extra_body" not in plain


@pytest.mark.parametrize(
    "finish,tool_calls,expected",
    [
        ("stop", None, "end_turn"),
        ("length", None, "max_tokens"),
        ("tool_calls", [("c1", "f", "{}")], "tool_use"),
        ("stop", [("c1", "f", "{}")], "tool_use"),  # some models misreport it
        ("content_filter", None, "content_filter"),
    ],
)
def test_openrouter_finish_reason(finish, tool_calls, expected):
    from openai.types.chat import ChatCompletion

    from app.llm import openrouter

    _, body = completion("x", tool_calls, finish)
    reply = openrouter.to_reply("m", ChatCompletion.model_validate(body))
    assert reply.stop_reason == expected


def test_openrouter_response_translation(tmp_path):
    llm, _ = openrouter_llm(
        tmp_path, completion("Hi.", [("c1", "f", '{"x": 2}'), ("c2", "g", "{not json")])
    )
    r = llm.complete("hello")
    assert r.reply.content == [
        {"text": "Hi."},
        {"toolUse": {"toolUseId": "c1", "name": "f", "input": {"x": 2}}},
        {"toolUse": {"toolUseId": "c2", "name": "g", "input": {"_raw": "{not json"}}},
    ]
    assert (r.reply.input_tokens, r.reply.cache_read_tokens, r.reply.output_tokens) == (60, 40, 20)
    assert r.stats.cost_usd == 0.0012  # OpenRouter's real cost, not the price table


def test_openrouter_extract_roundtrip(tmp_path):
    llm, server = openrouter_llm(
        tmp_path,
        completion(None, [("c1", "respond", '{"name": 7}')], "tool_calls"),  # invalid -> retry
        completion(None, [("c2", "respond", '{"name": "Ann"}')], "tool_calls"),
    )
    obj, _ = llm.extract("who", Party, system="Be exact.")
    assert obj.name == "Ann"
    first, retry = server.bodies
    assert first["tool_choice"] == {"type": "function", "function": {"name": "respond"}}
    assert first["provider"] == {"require_parameters": True}
    assert first["messages"][0] == {"role": "system", "content": "Be exact."}
    assert [m["role"] for m in retry["messages"]] == ["system", "user", "assistant", "tool"]
    assert retry["messages"][-1]["tool_call_id"] == "c1"


def test_openrouter_agent_two_turns(tmp_path):
    llm, server = openrouter_llm(
        tmp_path,
        completion("Checking.", [("c1", "lookup", '{"client_id": "C1"}')], "tool_calls"),
        completion("C1 is fine.", cost=0.002),
    )

    @tool
    def lookup(client_id: str) -> dict:
        """Look up a client."""
        return {"id": client_id, "ok": True}

    result = llm.run_agent("check C1", tools=[lookup], effort="high")
    assert result.text == "C1 is fine."
    assert [s.kind for s in result.steps] == ["text", "tool_call", "tool_result", "text"]
    assert result.cost_usd == pytest.approx(0.0032)
    second = server.bodies[1]
    assert second["reasoning"] == {"effort": "high"}
    assert second["tools"][0]["function"]["name"] == "lookup"
    assert second["messages"][-2]["tool_calls"][0]["function"]["arguments"] == (
        '{"client_id": "C1"}'
    )
    assert second["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": '{"id": "C1", "ok": true}',
    }


def test_openrouter_stream(tmp_path):
    def chunk(**kw):
        base = {"id": "gen-1", "object": "chat.completion.chunk", "created": 1, "model": "m"}
        return "data: " + json.dumps(base | kw) + "\n\n"

    sse = (
        chunk(choices=[{"index": 0, "delta": {"role": "assistant", "content": "Hel"}}])
        + chunk(choices=[{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}])
        + chunk(choices=[], usage={"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001})
        + "data: [DONE]\n\n"
    )
    llm, server = openrouter_llm(tmp_path, (200, sse))
    s = llm.stream("hi")
    assert list(s) == ["Hel", "lo"]
    assert s.result.text == "Hello" and s.result.reply.stop_reason == "end_turn"
    assert s.result.stats.output_tokens == 2 and s.result.stats.cost_usd == 0.0001
    assert server.bodies[0]["stream"] is True


def test_openrouter_extract_falls_back_only_on_tool_errors(tmp_path):
    import openai

    no_endpoints = {"error": {"code": 404, "message": "No endpoints found that support tool use."}}
    llm, server = openrouter_llm(
        tmp_path,
        (404, no_endpoints),  # "tool" mode
        (404, no_endpoints),  # "any" mode
        completion('Sure: {"name": "Ann"}'),  # "json" mode
        (402, {"error": {"code": 402, "message": "Insufficient credits"}}),
    )
    obj, _ = llm.extract("who", Party)
    assert obj.name == "Ann" and llm._extract_mode["openai/gpt-oss-120b"] == "json"
    assert server.bodies[1]["tool_choice"] == "required"
    assert "tools" not in server.bodies[2]
    with pytest.raises(openai.APIStatusError, match="Insufficient credits"):
        llm.extract("who", Party, model="openai/gpt-oss-20b")  # not a tool problem: raised
