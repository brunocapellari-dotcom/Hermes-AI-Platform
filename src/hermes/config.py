from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HERMES_", env_file=".env", extra="ignore", case_sensitive=False
    )

    environment: str = "production"
    database_url: str = "sqlite:///./hermes.db"
    dbos_system_database_url: str | None = None
    dbos_application_name: str = "hermes-worker"
    dbos_queue_name: str = "hermes-missions"
    model_gateway_url: str | None = None
    model_gateway_api_key: SecretStr | None = None
    default_model: str | None = None
    holding_url: str | None = None
    second_brain_url: str | None = None
    research_url: str | None = None
    allow_external_actions: bool = False
    auto_create_schema: bool = False
    request_timeout_seconds: float = 20.0

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
