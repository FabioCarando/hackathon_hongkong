"""USD per million tokens, Bedrock on-demand prices (US regions). Prices vary by region and change
over time, so treat these as estimates and check https://aws.amazon.com/bedrock/pricing/.
OpenRouter reports the real cost of each call, so this is only its fallback (and the fake's)."""

import re

# (input, output) per 1M tokens, keyed by base model (see `base_model`).
# Cache reads bill at 0.1x input, cache writes at 1.25x (only models that support prompt caching).
PRICES: dict[str, tuple[float, float]] = {
    "amazon.nova-micro": (0.035, 0.14),
    "amazon.nova-lite": (0.06, 0.24),
    "amazon.nova-pro": (0.80, 3.20),
    "amazon.nova-premier": (2.50, 12.50),
    "meta.llama4-maverick-17b-instruct": (0.24, 0.97),
    "meta.llama4-scout-17b-instruct": (0.17, 0.66),
    "meta.llama3-3-70b-instruct": (0.72, 0.72),
    "mistral.mistral-large-3": (0.50, 1.50),
    "deepseek.v3-2": (0.62, 1.85),
    "qwen.qwen3-32b": (0.15, 0.60),
    "openai.gpt-oss-120b": (0.15, 0.60),
    "openai.gpt-oss-20b": (0.07, 0.20),
    "anthropic.claude-sonnet-5": (2.0, 10.0),
    "anthropic.claude-haiku-4-5": (1.0, 5.0),
}

_GEO_PREFIX = re.compile(r"^(us|eu|apac|au|ca|jp|us-gov|global)\.")


def base_model(model_id: str) -> str:
    """'us.amazon.nova-pro-v1:0' -> 'amazon.nova-pro';
    'anthropic.claude-haiku-4-5-20251001-v1:0' -> 'anthropic.claude-haiku-4-5';
    OpenRouter 'openai/gpt-oss-120b:free' -> 'openai.gpt-oss-120b'."""
    if model_id.startswith("arn:"):
        name = model_id.rsplit("/", 1)[-1]  # inference-profile ARNs
    else:
        name = re.sub(r":[a-z]+$", "", model_id.replace("/", ".", 1))  # slug + variant
    name = _GEO_PREFIX.sub("", name)
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
