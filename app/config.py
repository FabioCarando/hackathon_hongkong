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

    aws_region: str = "us-west-2"
    aws_profile: str | None = None

    llm_provider: Literal["bedrock", "fake"] = "bedrock"
    bedrock_client: Literal["mantle", "runtime"] = "mantle"
    llm_model: str = "anthropic.claude-opus-5"
    llm_model_fast: str = "anthropic.claude-haiku-4-5"
    llm_max_tokens: int = 16000
    llm_cache: Literal["off", "on"] = "off"
    llm_log_path: str = "logs/llm_calls.jsonl"
    llm_cache_dir: str = ".llm_cache"
    fake_latency: float = 1.0  # fake provider: 0 = instant, 1 = roughly real Claude speed


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
