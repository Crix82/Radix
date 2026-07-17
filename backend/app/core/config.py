from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Radix"
    debug: bool = False

    database_url: str = "postgresql+psycopg://radix:radix@localhost:5432/radix"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    llm_provider: str = "ollama"
    llm_model: str = "qwen3.5:9b-instruct-q4_K_M"
    llm_base_url: str = "http://localhost:11434/v1"

    embed_device: str = "auto"
    ocr_langs: str = "ita+eng+deu"
    sync_interval_min: int = 5
    data_dir: str = "./data"

    jwt_secret: str = "change-me-this-is-only-a-dev-placeholder-secret"
    jwt_expire_minutes: int = 60 * 12
    session_cookie: str = "radix_session"

    admin_email: str | None = None
    admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
