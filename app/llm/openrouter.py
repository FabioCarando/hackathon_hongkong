"""OpenRouter adapter: translates our Converse-shaped params to an OpenAI chat-completions request
and the response back to a `Reply`, so the rest of the wrapper never sees the difference.

Converse                                   OpenAI / OpenRouter
system [{"text"}]                          {"role": "system"} message
assistant {"toolUse"} blocks               assistant "tool_calls" (arguments as a JSON string)
user {"toolResult"} blocks                 {"role": "tool", "tool_call_id"} messages
toolConfig.tools / toolChoice              tools / tool_choice
additionalModelRequestFields               extra body fields (e.g. OpenRouter's "reasoning")
"""

import json
from collections.abc import Iterator
from typing import Any

import openai

from app.config import Settings
from app.llm.reply import Reply

STOP_REASONS = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}


def client(cfg: Settings) -> openai.OpenAI:
    if not cfg.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to .env (see .env.example).")
    headers = {"X-Title": cfg.openrouter_app_name} if cfg.openrouter_app_name else None
    return openai.OpenAI(
        api_key=cfg.openrouter_api_key,
        base_url=cfg.openrouter_base_url,
        default_headers=headers,
        timeout=300,
        max_retries=4,  # 408/429/5xx and connection errors, with backoff
    )


def _text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(b["text"] for b in blocks if "text" in b)


def _result_text(result: dict[str, Any]) -> str:
    return "\n".join(
        c["text"] if "text" in c else json.dumps(c.get("json")) for c in result["content"]
    )


def _messages(params: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if params.get("system"):
        out.append({"role": "system", "content": "\n\n".join(b["text"] for b in params["system"])})
    for m in params["messages"]:
        blocks = m["content"]
        if m["role"] == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": _text(blocks) or None}
            calls = [
                {
                    "id": b["toolUse"]["toolUseId"],
                    "type": "function",
                    "function": {
                        "name": b["toolUse"]["name"],
                        "arguments": json.dumps(b["toolUse"]["input"]),
                    },
                }
                for b in blocks
                if "toolUse" in b
            ]
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        # tool results must directly follow the assistant turn that asked for them
        for b in blocks:
            if "toolResult" in b:
                r = b["toolResult"]
                out.append(
                    {"role": "tool", "tool_call_id": r["toolUseId"], "content": _result_text(r)}
                )
        if text := _text(blocks):
            out.append({"role": "user", "content": text})
    return out


def _tool_choice(choice: dict[str, Any]) -> Any:
    if "tool" in choice:
        return {"type": "function", "function": {"name": choice["tool"]["name"]}}
    return "required" if "any" in choice else "auto"


def request(params: dict[str, Any], stream: bool = False) -> dict[str, Any]:
    """Keyword arguments for `chat.completions.create`."""
    kwargs: dict[str, Any] = {
        "model": params["modelId"],
        "messages": _messages(params),
        "max_tokens": params["inferenceConfig"]["maxTokens"],
    }
    # usage (incl. real cost) is always returned by OpenRouter; `usage.include` is deprecated
    extra = dict(params.get("additionalModelRequestFields", {}))
    if tool_config := params.get("toolConfig"):
        kwargs["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["toolSpec"]["name"],
                    "description": t["toolSpec"]["description"],
                    "parameters": t["toolSpec"]["inputSchema"]["json"],
                },
            }
            for t in tool_config["tools"]
        ]
        if "toolChoice" in tool_config:
            kwargs["tool_choice"] = _tool_choice(tool_config["toolChoice"])
        # only route to upstream providers that actually support tools / tool_choice
        extra["provider"] = {"require_parameters": True}
    if extra:
        kwargs["extra_body"] = extra
    if stream:
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
    return kwargs


def create(client: openai.OpenAI, params: dict[str, Any], stream: bool = False) -> Any:
    return client.chat.completions.create(**request(params, stream))


def _arguments(raw: str | None) -> dict[str, Any]:
    try:
        args = json.loads(raw or "{}")
    except ValueError:
        return {"_raw": raw}  # fails tool/schema validation, which is reported back to the model
    return args if isinstance(args, dict) else {"_raw": raw}


def _reply(model: str, text: str, tool_calls: list[Any], finish: str | None, usage: Any) -> Reply:
    content: list[dict[str, Any]] = [{"text": text}] if text else []
    for i, call in enumerate(tool_calls):
        content.append(
            {
                "toolUse": {
                    "toolUseId": call.id or f"call_{i}",
                    "name": call.function.name,
                    "input": _arguments(call.function.arguments),
                }
            }
        )
    # some models say "stop" even when they called a tool; the agent loop keys off tool_use
    stop = "tool_use" if tool_calls else STOP_REASONS.get(finish or "", finish)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = (getattr(details, "cached_tokens", None) or 0) if details else 0
    return Reply(
        model=model,
        content=content,
        stop_reason=stop,
        # prompt_tokens includes cache reads; Converse counts them separately
        input_tokens=(usage.prompt_tokens - cached) if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        cache_read_tokens=cached,
        cost_usd=getattr(usage, "cost", None) if usage else None,
    )


def to_reply(model: str, completion: Any) -> Reply:
    if not completion.choices:
        error = getattr(completion, "error", None)
        raise RuntimeError(f"OpenRouter returned no answer: {error or completion}")
    choice = completion.choices[0]
    msg = choice.message
    return _reply(
        model, msg.content or "", msg.tool_calls or [], choice.finish_reason, completion.usage
    )


def stream_reply(model: str, chunks: Iterator[Any]):
    """Yields text deltas; returns the final `Reply` (generator return value)."""
    parts: list[str] = []
    finish, usage = None, None
    for chunk in chunks:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if text := choice.delta.content:
            parts.append(text)
            yield text
        finish = choice.finish_reason or finish
    return _reply(model, "".join(parts), [], finish, usage)


def rejection(e: Exception) -> str | None:
    """The message of a "this request is invalid" error (400/404), else None."""
    if isinstance(e, openai.APIStatusError) and e.status_code in (400, 404):
        return str(e)
    return None
