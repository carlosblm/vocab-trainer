"""Carga de la configuración de la aplicación desde variables de entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
