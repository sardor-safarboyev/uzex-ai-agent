"""Central application settings, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UZEX_")

    app_name: str = "UZEX AI Agent"


@lru_cache
def get_settings() -> Settings:
    return Settings()
