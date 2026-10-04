"""All settings come from environment variables / `.env`. Import `settings` anywhere."""

import os
from functools import lru_cache
from typing import Literal

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

# boto3 / the Bedrock client read AWS_* from the process environment, not from Settings,
# so export non-empty .env values (real env vars win).
for _k, _v in dotenv_values(".env").items():
    if _v and _k not in os.environ:
        os.environ[_k] = _v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_name: str | None = None  # sent as X-Title: shows in OpenRouter's usage pages

    # bedrock only
    aws_region: str = "us-west-2"
    aws_profile: str | None = None

    llm_provider: Literal["openrouter", "bedrock", "fake"] = "openrouter"
    # A model ID for the provider: an OpenRouter slug (https://openrouter.ai/models), or a Bedrock
    # model / inference-profile ID. Run scripts/check_env.py to see what works.
    llm_model: str = "openai/gpt-oss-120b"
    llm_model_fast: str = "openai/gpt-oss-20b"
    llm_max_tokens: int = 4096  # reserved against your credits (OpenRouter) / quota (Bedrock)
    llm_cache: Literal["off", "on"] = "off"
    llm_log_path: str = "logs/llm_calls.jsonl"
    llm_cache_dir: str = ".llm_cache"
    fake_latency: float = 1.0  # fake provider: 0 = instant, 1 = roughly real model speed
    llm_model_vision: str | None = None  # multimodal model for OCR of scanned PDFs

    # Trace
    trace_workspace: str = "runtime/workspace"  # where the app reads and writes
    trace_seed_workspace: str = "workspace"  # pristine copy, never written by the app
    # pre-computed OCR / extraction / question results by file hash (scripts/warm_demo_cache.py);
    # the demo documents then process instantly, anything else goes to the LLM as usual
    trace_demo_cache: str = "demo_cache"
    trace_user: str = "Jason Yip"  # default "Working as" user (must be in COMPANY.md)
    # live demo mailbox (IMAP, e.g. Gmail + app password); only subjects containing the tag are read
    trace_imap_host: str = "imap.gmail.com"
    trace_imap_user: str | None = None
    trace_imap_password: str | None = None
    trace_mail_tag: str = "Family Office Inquiry"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
