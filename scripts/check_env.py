"""First thing to run at kickoff: `uv run python scripts/check_env.py`

Checks AWS credentials, lists the Claude models this account can reach on Bedrock,
then makes one real call per configured model through our own wrapper.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3  # noqa: E402

from app.config import settings  # noqa: E402
from app.llm import get_llm  # noqa: E402
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


print(
    f"region={settings.aws_region} client={settings.bedrock_client} provider={settings.llm_provider}"
)
session = boto3.Session(profile_name=settings.aws_profile or None, region_name=settings.aws_region)

check("AWS identity", lambda: session.client("sts").get_caller_identity()["Arn"])

bedrock = session.client("bedrock")
check(
    "Anthropic foundation models",
    lambda: sorted(
        m["modelId"]
        for m in bedrock.list_foundation_models(byProvider="anthropic")["modelSummaries"]
    ),
)
check(
    "Anthropic inference profiles",
    lambda: sorted(
        p["inferenceProfileId"]
        for p in bedrock.list_inference_profiles(maxResults=1000)["inferenceProfileSummaries"]
        if "anthropic" in p["inferenceProfileId"]
    ),
)

llm = get_llm()
for label, fast in [("LLM_MODEL", False), ("LLM_MODEL_FAST", True)]:

    def ping(fast=fast):
        r = llm.complete("Reply with exactly: pong", fast=fast, max_tokens=50, label="check_env")
        s = r.stats
        return f"{s.model} -> {r.text!r} in {s.latency_ms / 1000:.2f}s, {fmt_cost(s.cost_usd)}"

    check(f"live call {label}", ping)

if failed:
    print(
        "\nHints: wrong model ID -> pick one from the lists above and set LLM_MODEL in .env;"
        "\n       Mantle not available in region -> set BEDROCK_CLIENT=runtime and use an"
        "\n       inference profile ID (e.g. global.anthropic...); AccessDenied -> ask organisers."
    )
sys.exit(1 if failed else 0)
