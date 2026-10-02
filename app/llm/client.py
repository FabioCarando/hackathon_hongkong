"""Thin wrapper over Claude on Amazon Bedrock.

Every call goes through `LLM._create`, which handles the disk cache, the fake provider,
latency/cost measurement and logging. Product code should only use the public methods:

    llm = get_llm()
    llm.complete("Summarise this ...")                  -> Result
    llm.extract("Pull fields from ...", MyModel)        -> (MyModel, Result)
    llm.stream("Explain ...")                           -> StreamResult (iterate for text)
    llm.run_agent("Investigate ...", tools=[my_tool])   -> AgentResult
"""

import hashlib
import inspect
import json
import time
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import Message
from pydantic import BaseModel, create_model

from app.config import Settings, settings
from app.llm import telemetry
from app.llm.fake import fake_message
from app.llm.pricing import cost_usd
from app.llm.telemetry import CallStats

Prompt = str | list[dict[str, Any]]


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
        """Build a tool from a typed function. Its docstring is what Claude reads."""
        fields: dict[str, Any] = {}
        hints = typing.get_type_hints(fn)
        for name, param in inspect.signature(fn).parameters.items():
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[name] = (hints.get(name, str), default)
        args_model = create_model(f"{fn.__name__}_args", **fields)
        schema = args_model.model_json_schema()
        schema.pop("title", None)
        return cls(
            name=fn.__name__,
            description=inspect.getdoc(fn) or fn.__name__,
            input_schema=schema,
            fn=fn,
            args_model=args_model,
            example=example,
        )

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
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
    message: Message


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


def _text(message: Message) -> str:
    return "".join(b.text for b in message.content if b.type == "text")


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, type) and issubclass(obj, BaseModel):
        return obj.model_json_schema()
    return str(obj)


class LLM:
    def __init__(self, cfg: Settings = settings):
        self.cfg = cfg
        self._client: anthropic.AnthropicBedrockMantle | anthropic.AnthropicBedrock | None = None

    @property
    def client(self):
        if self._client is None:
            kwargs = {
                "aws_region": self.cfg.aws_region,
                "aws_profile": self.cfg.aws_profile or None,
            }
            if self.cfg.bedrock_client == "mantle":
                self._client = anthropic.AnthropicBedrockMantle(**kwargs)
            else:
                self._client = anthropic.AnthropicBedrock(**kwargs)
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
        """Structured output: Claude's answer is validated into `schema`."""
        params = self._params(prompt, system, fast, model, None, None)
        result = self._create(params, label, schema=schema)
        return schema.model_validate_json(result.text), result

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
        params["tools"] = [t.spec() for t in tools]
        out = AgentResult(text="")

        def emit(step: AgentStep) -> None:
            out.steps.append(step)
            if on_step:
                on_step(step)

        for turn in range(max_turns):
            result = self._create(params, f"{label}#{turn}", tools=tools)
            out.calls.append(result.stats)
            msg = result.message
            params["messages"] = [
                *params["messages"],
                {"role": "assistant", "content": msg.content},
            ]
            if result.text:
                emit(AgentStep("text", data=result.text))
            if msg.stop_reason == "pause_turn":
                continue
            if msg.stop_reason != "tool_use":
                out.text = result.text
                return out

            tool_results = []
            for block in msg.content:
                if block.type != "tool_use":
                    continue
                emit(AgentStep("tool_call", block.name, block.input))
                try:
                    content, is_error = by_name[block.name].run(block.input), False
                except Exception as e:  # report tool errors back to Claude instead of crashing
                    content, is_error = f"{type(e).__name__}: {e}", True
                emit(AgentStep("tool_result", block.name, content, is_error))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
            params["messages"] = [*params["messages"], {"role": "user", "content": tool_results}]

        out.text = "(stopped: max_turns reached)"
        return out

    # -- internals ------------------------------------------------------------

    def _params(self, prompt, system, fast, model, max_tokens, effort) -> dict[str, Any]:
        messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
        params: dict[str, Any] = {
            "model": model or (self.cfg.llm_model_fast if fast else self.cfg.llm_model),
            "max_tokens": max_tokens or self.cfg.llm_max_tokens,
            "messages": messages,
        }
        if system:
            params["system"] = system
        if effort:
            params["output_config"] = {"effort": effort}
        return params

    def _cache_path(self, params: dict[str, Any], schema: type[BaseModel] | None) -> Path | None:
        if self.cfg.llm_cache != "on":
            return None
        key = json.dumps({"params": params, "schema": schema}, sort_keys=True, default=_jsonable)
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        return Path(self.cfg.llm_cache_dir) / f"{digest}.json"

    def _finish(self, message: Message, label: str, started: float, cached: bool) -> Result:
        u = message.usage
        stats = CallStats(
            model=message.model,
            label=label,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            cached=cached,
            stop_reason=message.stop_reason,
        )
        stats.cost_usd = (
            None
            if cached
            else cost_usd(
                message.model,
                stats.input_tokens,
                stats.output_tokens,
                stats.cache_read_tokens,
                stats.cache_write_tokens,
            )
        )
        telemetry.record(stats)
        return Result(text=_text(message), stats=stats, message=message)

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
            return self._finish(Message.model_validate_json(path.read_text()), label, started, True)

        if self.cfg.llm_provider == "fake":
            message = fake_message(params, schema, tools, self.cfg.fake_latency)
        elif schema is not None:
            message = self.client.messages.parse(**params, output_format=schema)
        else:
            message = self.client.messages.create(**params)

        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(Message.model_validate(message.model_dump()).model_dump_json())
        return self._finish(message, label, started, False)

    def _stream(self, params: dict[str, Any], label: str):
        path = self._cache_path(params, None)
        if self.cfg.llm_provider == "fake" or (path and path.exists()):
            result = self._create(params, label)
            for i in range(0, len(result.text), 24):  # replay in chunks so the UI still "types"
                yield result.text[i : i + 24]
                time.sleep(0.01)
            return result

        started = time.perf_counter()
        with self.client.messages.stream(**params) as s:
            yield from s.text_stream
            message = s.get_final_message()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(message.model_dump_json())
        return self._finish(message, label, started, False)


@lru_cache
def get_llm() -> LLM:
    return LLM()
