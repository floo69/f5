from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    orchestrator_model: str = "claude-opus-5-5"
    worker_model: str = "claude-opus-5-5"
    browser_allowlist: str = "localhost:8100"
    jev_api_key: str = ""
    jev_base_url: str = ""

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.browser_allowlist.split(",") if h.strip()]


settings = Settings()
