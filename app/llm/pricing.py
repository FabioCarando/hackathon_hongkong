"""USD per million tokens. Anthropic list prices: Bedrock bills about the same for
global inference profiles, and some regional endpoints charge more, so treat these as estimates."""

import re

# (input, output) per 1M tokens. Cache reads bill at 0.1x input, cache writes at 1.25x.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def base_model(model_id: str) -> str:
    """'global.anthropic.claude-opus-5-v1:0' -> 'claude-opus-5'."""
    name = model_id.split("anthropic.")[-1]
    name = re.sub(r"-v\d+(:\d+)?$", "", name)
    name = re.sub(r"-\d{8}$", "", name)
    return name


def cost_usd(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float | None:
    price = PRICES.get(base_model(model_id))
    if price is None:
        return None
    p_in, p_out = price
    return (
        input_tokens * p_in
        + output_tokens * p_out
        + cache_read * p_in * 0.1
        + cache_write * p_in * 1.25
    ) / 1_000_000
