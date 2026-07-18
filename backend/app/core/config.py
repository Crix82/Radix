from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Radix"
    debug: bool = False

    database_url: str = "postgresql+pg8000://radix:radix@localhost:5432/radix"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    llm_provider: str = "ollama"
    llm_model: str = "qwen3.5:9b-q4_K_M"
    llm_base_url: str = "http://localhost:11434/v1"
    # Refusal threshold on the best dense cosine. Calibrated in M4: answerable eval
    # questions score >= 0.52, so 0.45 leaves margin while refusing clearly-unrelated
    # queries; borderline off-corpus (e.g. a nearby-but-absent model) is caught by the
    # LLM grounding. Override in the `settings` table (`refusal_threshold`). See ADR 0005.
    refusal_threshold: float = 0.45

    embed_device: str = "auto"
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    qdrant_collection: str = "chunks"
    ocr_langs: str = "ita+eng+deu"
    sync_interval_min: int = 5
    data_dir: str = "./data"
    storage_capacity_gb: int = 500  # per-installation corpus budget (SPEC §1)

    jwt_secret: str = "change-me-this-is-only-a-dev-placeholder-secret"
    jwt_expire_minutes: int = 60 * 12
    session_cookie: str = "radix_session"

    admin_email: str | None = None
    admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
