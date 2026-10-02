"""Simulated Claude for LLM_PROVIDER=fake: no network, no credentials, no cost.

Behaves enough like the real thing to build and demo the UI against it:
- realistic latency and token counts (so cost/latency panels show plausible numbers)
- streaming text
- structured output that validates against the requested pydantic schema
- agent loops that really call your tools (with each tool's `example` args), then answer
Outputs are deterministic per prompt, so reruns look stable.
"""

import hashlib
import json
import random
import time
import types
import typing
from typing import TYPE_CHECKING, Any

from anthropic.types import Message
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.llm.client import Tool


def _rng(params: dict[str, Any]) -> random.Random:
    seed = hashlib.sha256(json.dumps(params, default=str, sort_keys=True).encode()).hexdigest()
    return random.Random(seed)


def placeholder(annotation: Any, rng: random.Random, name: str = "value") -> Any:
    """A plausible value of any (nested) type, so fake output validates against the schema."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {n: placeholder(f.annotation, rng, n) for n, f in annotation.model_fields.items()}
    if origin is typing.Literal:
        return rng.choice(args)
    if origin in (list, set, tuple):
        item = args[0] if args else str
        return [placeholder(item, rng, name) for _ in range(rng.randint(1, 3))]
    if origin is dict:
        return {}
    if origin in (typing.Union, types.UnionType):
        return placeholder(next(a for a in args if a is not type(None)), rng, name)
    if annotation is bool:
        return rng.random() < 0.5
    if annotation is int:
        return rng.randint(1, 100)
    if annotation is float:
        return round(rng.random(), 2)
    return f"simulated {name.replace('_', ' ')} #{rng.randint(1, 99)}"


def _tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content = messages[-1]["content"]
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]


def _prose(prompt: str, rng: random.Random) -> str:
    topic = prompt.strip().splitlines()[0][:120] if prompt.strip() else "your request"
    points = rng.sample(
        [
            "the key driver is concentration of activity in a short time window",
            "the data is consistent with the stated client profile",
            "two signals point the same way, which raises confidence",
            "this would normally be routed to a human reviewer",
            "historical baselines suggest this is within the expected range",
            "a regulator would expect the reasoning and sources to be recorded",
        ],
        3,
    )
    bullets = "\n".join(f"- {p.capitalize()}." for p in points)
    return f"**Simulated answer** to: _{topic}_\n\n{bullets}\n\nNo model was called (LLM_PROVIDER=fake)."


def fake_message(
    params: dict[str, Any],
    schema: type[BaseModel] | None,
    tools: "list[Tool] | None",
    latency: float,
) -> Message:
    rng = _rng(params)
    messages = params["messages"]
    content: list[dict[str, Any]]
    stop_reason = "end_turn"

    if schema is not None:
        content = [{"type": "text", "text": json.dumps(placeholder(schema, rng))}]
    elif tools and not _tool_results(messages):
        stop_reason = "tool_use"
        content = [{"type": "text", "text": "Let me look that up."}]
        for i, t in enumerate(tools):
            args = t.example or {
                n: placeholder(f.annotation, rng, n) for n, f in t.args_model.model_fields.items()
            }
            content.append(
                {"type": "tool_use", "id": f"toolu_fake_{i}", "name": t.name, "input": args}
            )
    elif tools:
        lines = "\n".join(
            f"- `{r['tool_use_id']}` returned: {str(r['content'])[:200]}"
            for r in _tool_results(messages)
        )
        text = f"**Simulated conclusion** from the tool results:\n\n{lines}"
        content = [{"type": "text", "text": text}]
    else:
        first = messages[-1]["content"]
        content = [{"type": "text", "text": _prose(str(first), rng)}]

    out_text = json.dumps(content)
    usage = {
        "input_tokens": len(json.dumps(params, default=str)) // 4,
        "output_tokens": len(out_text) // 4,
    }
    if latency:
        time.sleep(latency * (0.3 + usage["output_tokens"] * 0.004 + rng.random() * 0.4))
    return Message.model_validate(
        {
            "id": f"msg_fake_{rng.randint(0, 10**8)}",
            "type": "message",
            "role": "assistant",
            "model": params["model"],
            "content": content,
            "stop_reason": stop_reason,
            "usage": usage,
        }
    )
