"""One model response, in Bedrock Converse shape, independent of which provider/model produced it."""

from typing import Any

from pydantic import BaseModel


class Reply(BaseModel):
    model: str
    # Converse content blocks: {"text": ...}, {"toolUse": {"toolUseId", "name", "input"}},
    # {"reasoningContent": ...}. Sent back verbatim as the assistant turn in agent loops.
    content: list[dict[str, Any]]
    stop_reason: str | None = None  # "end_turn" | "tool_use" | "max_tokens" | ...
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None  # real cost when the provider reports it (OpenRouter)

    @property
    def text(self) -> str:
        return "".join(b["text"] for b in self.content if "text" in b)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """[{"toolUseId", "name", "input"}, ...]"""
        return [b["toolUse"] for b in self.content if "toolUse" in b]

    @classmethod
    def from_converse(cls, model: str, response: dict[str, Any]) -> "Reply":
        u = response.get("usage", {})
        return cls(
            model=model,
            content=response["output"]["message"]["content"],
            stop_reason=response.get("stopReason"),
            input_tokens=u.get("inputTokens", 0),
            output_tokens=u.get("outputTokens", 0),
            cache_read_tokens=u.get("cacheReadInputTokens", 0),
            cache_write_tokens=u.get("cacheWriteInputTokens", 0),
        )
