"""Thin wrapper over any text model on OpenRouter (default) or Amazon Bedrock.

Internally everything is Bedrock Converse-shaped (params, content blocks, `Reply`); the OpenRouter
adapter (`openrouter.py`) translates at the boundary. Switch model with `LLM_MODEL` /
`LLM_MODEL_FAST` and provider with `LLM_PROVIDER`: the code below doesn't change. Every call goes
through `LLM._create`, which handles the disk cache, the fake provider, latency/cost measurement
and logging. Product code should only use the public methods:

    llm = get_llm()
    llm.complete("Summarise this ...")                  -> Result
    llm.extract("Pull fields from ...", MyModel)        -> (MyModel, Result)
    llm.stream("Explain ...")                           -> StreamResult (iterate for text)
    llm.run_agent("Investigate ...", tools=[my_tool])   -> AgentResult
"""

import hashlib
import inspect
import json
import re
import time
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError, create_model

from app.config import Settings, settings
from app.llm import openrouter, telemetry
from app.llm.fake import fake_reply
from app.llm.pricing import base_model, cost_usd
from app.llm.reply import Reply
from app.llm.telemetry import CallStats

# A string, or Converse messages: [{"role": "user", "content": "..." | [{"text": "..."}]}, ...]
Prompt = str | list[dict[str, Any]]

RESPOND_TOOL = "respond"  # the tool `extract` forces the model to call with its structured answer


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic emits `$defs` + `$ref`; not every model resolves them, so inline them."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _json_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = _inline_refs(model.model_json_schema())
    schema.pop("title", None)
    return schema


# --------------------------------------------------------------------------- tools


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]
    args_model: type[BaseModel]
    example: dict[str, Any] | None = None  # args the fake provider uses when "calling" it

    @classmethod
    def from_function(cls, fn: Callable[..., Any], example: dict[str, Any] | None = None) -> "Tool":
        """Build a tool from a typed function. Its docstring is what the model reads."""
        fields: dict[str, Any] = {}
        hints = typing.get_type_hints(fn)
        for name, param in inspect.signature(fn).parameters.items():
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[name] = (hints.get(name, str), default)
        args_model = create_model(f"{fn.__name__}_args", **fields)
        return cls(
            name=fn.__name__,
            description=inspect.getdoc(fn) or fn.__name__,
            input_schema=_json_schema(args_model),
            fn=fn,
            args_model=args_model,
            example=example,
        )

    def spec(self) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": self.name,
                "description": self.description,
                "inputSchema": {"json": self.input_schema},
            }
        }

    def run(self, args: dict[str, Any]) -> str:
        validated = self.args_model.model_validate(args)
        out = self.fn(**validated.model_dump())
        if isinstance(out, BaseModel):
            return out.model_dump_json()
        return out if isinstance(out, str) else json.dumps(out, default=str)


def tool(fn: Callable[..., Any] | None = None, *, example: dict[str, Any] | None = None):
    """Decorator: `@tool` or `@tool(example={"client_id": "C-1"})` on a typed, documented function.

    `example` is only used by the fake provider, so agent flows can be tested offline."""
    if fn is None:
        return lambda f: Tool.from_function(f, example)
    return Tool.from_function(fn, example)


# --------------------------------------------------------------------------- results


@dataclass
class Result:
    text: str
    stats: CallStats
    reply: Reply


@dataclass
class AgentStep:
    kind: str  # "text" | "tool_call" | "tool_result"
    name: str = ""
    data: Any = None
    is_error: bool = False


@dataclass
class AgentResult:
    text: str
    steps: list[AgentStep] = field(default_factory=list)
    calls: list[CallStats] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd or 0 for c in self.calls)

    @property
    def latency_ms(self) -> float:
        return sum(c.latency_ms for c in self.calls)


class StreamResult:
    """Iterate to get text chunks (works with `st.write_stream`); `.result` is set afterwards."""

    def __init__(self, gen: Iterator[str]):
        self._gen = gen
        self.result: Result | None = None

    def __iter__(self) -> Iterator[str]:
        self.result = yield from self._gen


# --------------------------------------------------------------------------- client


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, type) and issubclass(obj, BaseModel):
        return obj.model_json_schema()
    return str(obj)


def _messages(prompt: Prompt) -> list[dict[str, Any]]:
    if isinstance(prompt, str):
        prompt = [{"role": "user", "content": prompt}]
    return [
        {**m, "content": [{"text": m["content"]}]} if isinstance(m["content"], str) else m
        for m in prompt
    ]


def _effort_fields(provider: str, model_id: str, effort: str) -> dict[str, Any]:
    """Reasoning effort has no portable Converse field; map it per provider / model."""
    if provider == "openrouter":
        return {"reasoning": {"effort": effort}}  # OpenRouter maps it to each model's own knob
    name = base_model(model_id)
    if name.startswith("openai.gpt-oss"):
        return {"reasoning_effort": effort}
    if name.startswith("amazon.nova-2"):
        return {"reasoningConfig": {"type": "enabled", "maxReasoningEffort": effort}}
    return {}  # other models: ignored


def _rejection(e: Exception) -> str | None:
    """The message of a provider's "this request is invalid" error, else None."""
    resp = getattr(e, "response", None)
    if isinstance(resp, dict) and resp.get("Error", {}).get("Code") == "ValidationException":
        return resp["Error"]["Message"]  # botocore ClientError, matched without importing botocore
    return openrouter.rejection(e)


def _tool_unsupported(e: Exception) -> bool:
    """Model/provider can't do tools or this tool_choice (OpenRouter: "No endpoints found ...")."""
    msg = (_rejection(e) or "").lower()
    return "tool" in msg or "requested parameters" in msg


def _token_limit(e: Exception) -> int | None:
    """The model's output-token limit, if `e` says we asked for more than it."""
    msg = _rejection(e) or ""
    match = re.search(r"(?:model limit of|at most|less than or equal to) `?(\d+)", msg)
    return int(match.group(1)) if match and "token" in msg.lower() else None


def _parse_json(text: str) -> Any:
    """JSON from a model's text answer, tolerating ```json fences and chatter around it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


class LLM:
    def __init__(self, cfg: Settings = settings):
        self.cfg = cfg
        self._client = None
        # extract strategy that worked per model: "tool" | "any" | "json" (see `extract`)
        self._extract_mode: dict[str, str] = {}
        # output-token limit per model, learned from the provider's error when we ask for more
        self._max_tokens: dict[str, int] = {}

    @property
    def client(self):
        if self._client is None and self.cfg.llm_provider == "openrouter":
            self._client = openrouter.client(self.cfg)
        elif self._client is None:
            import boto3  # lazy: only needed (and configured) for the Bedrock provider
            from botocore.config import Config

            session = boto3.Session(
                profile_name=self.cfg.aws_profile or None, region_name=self.cfg.aws_region
            )
            self._client = session.client(
                "bedrock-runtime",
                config=Config(read_timeout=300, retries={"max_attempts": 4, "mode": "adaptive"}),
            )
        return self._client

    # -- public API -----------------------------------------------------------

    def complete(
        self,
        prompt: Prompt,
        *,
        system: str | None = None,
        fast: bool = False,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str | None = None,
        label: str = "complete",
    ) -> Result:
        params = self._params(prompt, system, fast, model, max_tokens, effort)
        return self._create(params, label)

    def extract[T: BaseModel](
        self,
        prompt: Prompt,
        schema: type[T],
        *,
        system: str | None = None,
        fast: bool = False,
        model: str | None = None,
        label: str = "extract",
    ) -> tuple[T, Result]:
        """Structured output: the model's answer is validated into `schema`.

        The schema is sent as a tool the model is forced to call. Models that can't force a
        specific tool fall back to "call any tool", then to JSON in the text; the working mode is
        remembered per model. One retry if the answer doesn't validate."""
        params = self._params(prompt, system, fast, model, None, None)
        model_id = params["modelId"]
        modes = ["tool", "any", "json"]
        if model_id in self._extract_mode:
            modes = modes[modes.index(self._extract_mode[model_id]) :]

        for i, mode in enumerate(modes):
            try:
                sent, result = self._extract_call(params, schema, mode, label)
            except Exception as e:
                if not _tool_unsupported(e) or i == len(modes) - 1:
                    raise
                continue  # this model doesn't support `mode`; try the next one
            self._extract_mode[model_id] = mode
            return self._validate(sent, schema, label, result)
        raise AssertionError("unreachable")

    def stream(
        self,
        prompt: Prompt,
        *,
        system: str | None = None,
        fast: bool = False,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str | None = None,
        label: str = "stream",
    ) -> StreamResult:
        params = self._params(prompt, system, fast, model, max_tokens, effort)
        return StreamResult(self._stream(params, label))

    def run_agent(
        self,
        prompt: Prompt,
        tools: list[Tool],
        *,
        system: str | None = None,
        fast: bool = False,
        model: str | None = None,
        effort: str | None = None,
        max_turns: int = 10,
        on_step: Callable[[AgentStep], None] | None = None,
        label: str = "agent",
    ) -> AgentResult:
        """Tool-use loop. `on_step` fires for every text / tool call / tool result (for live UI)."""
        by_name = {t.name: t for t in tools}
        params = self._params(prompt, system, fast, model, None, effort)
        params["toolConfig"] = {"tools": [t.spec() for t in tools]}
        out = AgentResult(text="")

        def emit(step: AgentStep) -> None:
            out.steps.append(step)
            if on_step:
                on_step(step)

        for turn in range(max_turns):
            result = self._create(params, f"{label}#{turn}", tools=tools)
            out.calls.append(result.stats)
            reply = result.reply
            params["messages"] = [
                *params["messages"],
                {"role": "assistant", "content": reply.content},
            ]
            if result.text:
                emit(AgentStep("text", data=result.text))
            if reply.stop_reason != "tool_use":
                out.text = result.text
                return out

            tool_results = []
            for call in reply.tool_calls:
                emit(AgentStep("tool_call", call["name"], call["input"]))
                try:
                    content, is_error = by_name[call["name"]].run(call["input"]), False
                except Exception as e:  # report tool errors back to the model instead of crashing
                    content, is_error = f"ERROR {type(e).__name__}: {e}", True
                emit(AgentStep("tool_result", call["name"], content, is_error))
                # no "status": "error" field, since only some models accept it
                tool_results.append(
                    {"toolResult": {"toolUseId": call["toolUseId"], "content": [{"text": content}]}}
                )
            params["messages"] = [*params["messages"], {"role": "user", "content": tool_results}]

        out.text = "(stopped: max_turns reached)"
        return out

    # -- internals ------------------------------------------------------------

    def _params(self, prompt, system, fast, model, max_tokens, effort) -> dict[str, Any]:
        model_id = model or (self.cfg.llm_model_fast if fast else self.cfg.llm_model)
        params: dict[str, Any] = {
            "modelId": model_id,
            "messages": _messages(prompt),
            "inferenceConfig": {"maxTokens": self._cap(model_id, max_tokens)},
        }
        if system:
            params["system"] = [{"text": system}]
        if effort and (extra := _effort_fields(self.cfg.llm_provider, model_id, effort)):
            params["additionalModelRequestFields"] = extra
        return params

    def _cap(self, model_id: str, max_tokens: int | None) -> int:
        wanted = max_tokens or self.cfg.llm_max_tokens
        return min(wanted, self._max_tokens.get(model_id, wanted))

    def _send(self, params: dict[str, Any], stream: bool) -> Any:
        if self.cfg.llm_provider == "openrouter":
            return openrouter.create(self.client, params, stream)
        method = self.client.converse_stream if stream else self.client.converse
        return method(**params)

    def _converse(self, params: dict[str, Any], stream: bool = False) -> Any:
        """Call the provider; if maxTokens is above this model's limit, retry at the limit."""
        try:
            return self._send(params, stream)
        except Exception as e:
            limit = _token_limit(e)
            if limit is None:
                raise
            self._max_tokens[params["modelId"]] = limit
            config = {**params["inferenceConfig"], "maxTokens": limit}
            return self._send({**params, "inferenceConfig": config}, stream)

    def _extract_call(
        self, params: dict[str, Any], schema: type[BaseModel], mode: str, label: str
    ) -> tuple[dict[str, Any], Result]:
        """Returns the params actually sent (needed for the retry) and the result."""
        params = dict(params)
        if mode == "json":
            instructions = (
                "Answer with only a JSON object matching this JSON schema, no other text:\n"
                + json.dumps(_json_schema(schema))
            )
            prior = params.get("system", [])
            params["system"] = [*prior, {"text": instructions}]
        else:
            respond = {
                "toolSpec": {
                    "name": RESPOND_TOOL,
                    "description": "Return the final answer in this exact structure.",
                    "inputSchema": {"json": _json_schema(schema)},
                }
            }
            choice = {"tool": {"name": RESPOND_TOOL}} if mode == "tool" else {"any": {}}
            params["toolConfig"] = {"tools": [respond], "toolChoice": choice}
        return params, self._create(params, label, schema=schema)

    def _validate[T: BaseModel](
        self, sent: dict[str, Any], schema: type[T], label: str, result: Result
    ) -> tuple[T, Result]:
        for attempt in range(2):
            reply = result.reply
            try:
                call = next((c for c in reply.tool_calls if c["name"] == RESPOND_TOOL), None)
                data = call["input"] if call else _parse_json(reply.text)
                return schema.model_validate(data), result
            except (ValidationError, ValueError) as e:
                if attempt == 1:
                    raise
                # show the model its mistake and ask again
                feedback = f"That answer was invalid: {e}. Try again, fixing these errors."
                if call:
                    user = [
                        {
                            "toolResult": {
                                "toolUseId": call["toolUseId"],
                                "content": [{"text": feedback}],
                            }
                        }
                    ]
                else:
                    user = [{"text": feedback}]
                sent = {
                    **sent,
                    "messages": [
                        *sent["messages"],
                        {"role": "assistant", "content": reply.content},
                        {"role": "user", "content": user},
                    ],
                }
                result = self._create(sent, f"{label}:retry", schema=schema)
        raise AssertionError("unreachable")

    def _cache_path(self, params: dict[str, Any], schema: type[BaseModel] | None) -> Path | None:
        if self.cfg.llm_cache != "on":
            return None
        key = json.dumps({"params": params, "schema": schema}, sort_keys=True, default=_jsonable)
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        return Path(self.cfg.llm_cache_dir) / f"{digest}.json"

    def _finish(self, reply: Reply, label: str, started: float, cached: bool) -> Result:
        stats = CallStats(
            model=reply.model,
            label=label,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cache_read_tokens=reply.cache_read_tokens,
            cache_write_tokens=reply.cache_write_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            cached=cached,
            stop_reason=reply.stop_reason,
        )
        stats.cost_usd = (
            None
            if cached
            else reply.cost_usd
            if reply.cost_usd is not None
            else cost_usd(
                reply.model,
                stats.input_tokens,
                stats.output_tokens,
                stats.cache_read_tokens,
                stats.cache_write_tokens,
            )
        )
        telemetry.record(stats)
        return Result(text=reply.text, stats=stats, reply=reply)

    def _save(self, path: Path | None, reply: Reply) -> None:
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(reply.model_dump_json())

    def _create(
        self,
        params: dict[str, Any],
        label: str,
        schema: type[BaseModel] | None = None,
        tools: list[Tool] | None = None,
    ) -> Result:
        started = time.perf_counter()
        path = self._cache_path(params, schema)
        if path and path.exists():
            return self._finish(Reply.model_validate_json(path.read_text()), label, started, True)

        if self.cfg.llm_provider == "fake":
            reply = fake_reply(params, schema, tools, self.cfg.fake_latency)
        elif self.cfg.llm_provider == "openrouter":
            reply = openrouter.to_reply(params["modelId"], self._converse(params))
        else:
            reply = Reply.from_converse(params["modelId"], self._converse(params))

        self._save(path, reply)
        return self._finish(reply, label, started, False)

    def _stream(self, params: dict[str, Any], label: str):
        path = self._cache_path(params, None)
        if self.cfg.llm_provider == "fake" or (path and path.exists()):
            result = self._create(params, label)
            for i in range(0, len(result.text), 24):  # replay in chunks so the UI still "types"
                yield result.text[i : i + 24]
                time.sleep(0.01)
            return result

        started = time.perf_counter()
        if self.cfg.llm_provider == "openrouter":
            chunks = self._converse(params, stream=True)
            reply = yield from openrouter.stream_reply(params["modelId"], chunks)
        else:
            reply = yield from self._bedrock_stream(params)
        self._save(path, reply)
        return self._finish(reply, label, started, False)

    def _bedrock_stream(self, params: dict[str, Any]):
        chunks: list[str] = []
        stop_reason, usage = None, {}
        for event in self._converse(params, stream=True)["stream"]:
            if text := event.get("contentBlockDelta", {}).get("delta", {}).get("text"):
                chunks.append(text)
                yield text
            elif "messageStop" in event:
                stop_reason = event["messageStop"]["stopReason"]
            elif "metadata" in event:
                usage = event["metadata"].get("usage", {})
        return Reply.from_converse(
            params["modelId"],
            {
                "output": {
                    "message": {"role": "assistant", "content": [{"text": "".join(chunks)}]}
                },
                "stopReason": stop_reason,
                "usage": usage,
            },
        )


@lru_cache
def get_llm() -> LLM:
    return LLM()
