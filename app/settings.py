from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="E-commerce AI Operations Copilot")
    app_env: str = Field(default="local")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@postgres:5432/ops_copilot"
    )
    redis_url: str = Field(default="redis://redis:6379/0")
    kafka_bootstrap_servers: str = Field(default="redpanda:9092")
    kafka_topic: str = Field(default="operations.events")
    llm_provider: str = Field(default="mock")
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_model: str = Field(default="gpt-4o-mini")
    request_timeout_seconds: int = Field(default=10)
    approval_timeout_minutes: int = Field(default=60)
    worker_metrics_port: int = Field(default=9100)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

