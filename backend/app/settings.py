from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# USD per 1M tokens: (input, output, cache read). Used by the per-run budget guard.
PRICES_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    llm_provider: Literal["anthropic", "bedrock", "foundry"] = "anthropic"
    llm_mode: Literal["live", "replay", "off"] = "replay"
    max_usd_per_run: float = 0.50

    orchestrator_model: str = "claude-sonnet-5-5"
    auditor_model: str = "claude-sonnet-5-5"
    reviewer_model: str = "claude-sonnet-5-5"
    notice_model: str = "claude-haiku-5-5"

    browser_allowlist: str = "localhost:8100"
    aws_region: str = ""
    jev_api_key: str = ""
    jev_base_url: str = ""

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.browser_allowlist.split(",") if h.strip()]


settings = Settings()
