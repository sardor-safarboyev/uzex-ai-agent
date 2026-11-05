"""Central application settings, loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UZEX_")

    groq_api_key: SecretStr | None = Field(
        default=None, validation_alias="GROQ_API_KEY"
    )
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = Field(default=20, gt=0, le=120)
    groq_max_retries: int = Field(default=2, ge=0, le=3)
    groq_structured_output: bool = False
    openrouter_timeout_seconds: float = Field(default=20, gt=0, le=120)
    openrouter_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )
    openrouter_model: str = Field(
        default="nvidia/nemotron-3.5-lightning:free",
        validation_alias="OPENROUTER_MODEL",
    )

    production: bool = False
    cors_origins: list[str] = Field(default_factory=list)
    ask_max_concurrent: int = Field(default=4, ge=1, le=16)

    app_name: str = "UZEX AI Agent"
    database_path: Path | None = None
    database_metadata_enabled: bool = False
    query_max_results: int = Field(default=1000, ge=1, le=1000)
    database_threads: int = Field(default=2, ge=1, le=8)
    database_memory_mb: int = Field(default=256, ge=16, le=8192)
    database_max_connections: int = Field(default=2, ge=1, le=8)
    database_query_timeout_ms: int = Field(default=5000, ge=1, le=60000)
    database_metadata_max_columns: int = Field(default=2000, ge=1, le=10000)

    @field_validator("database_path", mode="before")
    @classmethod
    def file_path_only(cls, value: object) -> object:
        if value is not None:
            text = str(value).strip()
            if not text or text.startswith(":"):
                raise ValueError(
                    "database_path must be a file path, not an in-memory database"
                )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
