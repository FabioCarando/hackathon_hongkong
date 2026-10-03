"""First thing to run at kickoff: `uv run python scripts/check_env.py`

Checks AWS credentials, lists the text models this account can reach on Bedrock, then for each
configured model runs a ping, a tool call and a structured extract through our own wrapper.
Models differ a lot at tool use and structured output, so this tells us which to use for what.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typing import Literal  # noqa: E402

import boto3  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.config import settings  # noqa: E402
from app.llm import get_llm, tool  # noqa: E402
from app.ui.components import fmt_cost  # noqa: E402

OK, FAIL = "\033[32mOK  \033[0m", "\033[31mFAIL\033[0m"
failed = False


def check(name: str, fn) -> object:
    global failed
    try:
        out = fn()
        print(f"{OK} {name}: {out}")
        return out
    except Exception as e:
        failed = True
        print(f"{FAIL} {name}: {type(e).__name__}: {str(e)[:300]}")
        return None


print(f"region={settings.aws_region} provider={settings.llm_provider}")
session = boto3.Session(profile_name=settings.aws_profile or None, region_name=settings.aws_region)

check("AWS identity", lambda: session.client("sts").get_caller_identity()["Arn"])

bedrock = session.client("bedrock")


def text_models() -> str:
    models = bedrock.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]
    ids = sorted(
        m["modelId"]
        for m in models
        if m.get("modelLifecycle", {}).get("status") == "ACTIVE"
        and "ON_DEMAND" in m.get("inferenceTypesSupported", [])
    )
    return f"{len(ids)} on-demand\n     " + "\n     ".join(ids)


def profiles() -> str:
    summaries = bedrock.list_inference_profiles(maxResults=1000)["inferenceProfileSummaries"]
    ids = sorted(p["inferenceProfileId"] for p in summaries)
    return f"{len(ids)} (use these IDs for models that aren't on-demand)\n     " + "\n     ".join(
        ids
    )


check("Text models", text_models)
check("Inference profiles", profiles)


class Verdict(BaseModel):
    decision: Literal["escalate", "close"]
    reasons: list[str]


@tool(example={"pair": "USDHKD"})
def get_fx_rate(pair: str) -> float:
    """Spot FX rate for a currency pair written like USDHKD."""
    return 7.78


llm = get_llm()
for label, model in [
    ("LLM_MODEL", settings.llm_model),
    ("LLM_MODEL_FAST", settings.llm_model_fast),
]:
    print(f"\n{label} = {model}")

    def ping(model=model):
        r = llm.complete("Reply with exactly: pong", model=model, max_tokens=50, label="check_env")
        s = r.stats
        return f"{r.text.strip()!r} in {s.latency_ms / 1000:.2f}s, {fmt_cost(s.cost_usd)}"

    def tools(model=model):
        r = llm.run_agent(
            "What is 100 USD in HKD? Use the tool.", [get_fx_rate], model=model, max_turns=3
        )
        called = any(s.kind == "tool_call" for s in r.steps)
        if not called:
            raise RuntimeError(f"model answered without calling the tool: {r.text[:100]!r}")
        return f"{r.text.strip()[:80]!r} in {r.latency_ms / 1000:.2f}s"

    def structured(model=model):
        obj, _ = llm.extract(
            "Alert: 5 cash deposits of HKD 49,000 in one day.", Verdict, model=model
        )
        return f"{obj!r} via {llm._extract_mode.get(model)} mode"

    check("  ping", ping)
    check("  tool use", tools)
    check("  extract", structured)

if failed:
    print(
        "\nHints: model ID invalid or 'on-demand throughput isn't supported' -> use an ID from"
        "\n       the inference profiles list (e.g. us.amazon.nova-pro-v1:0) for LLM_MODEL;"
        "\n       AccessDenied -> enable the model in the Bedrock console or ask the organisers;"
        "\n       tool use fails -> pick another model for agents (pass model=... to run_agent);"
        "\n       'Too many tokens per day' -> the account's daily quota for that model is used up"
        "\n       or 0 (new accounts): request an increase in Service Quotas, or use another account;"
        "\n       'unsupported countries' -> provider geo-blocked; use Nova/Llama/gpt-oss/DeepSeek/..."
    )
sys.exit(1 if failed else 0)
