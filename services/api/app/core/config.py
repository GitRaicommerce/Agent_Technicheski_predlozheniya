from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://tpai:tpai_dev@localhost:5432/tpai"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket_files: str = "tp-files"
    minio_bucket_exports: str = "tp-exports"
    minio_secure: bool = False

    # LLM
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_default_provider: str = "openai"
    llm_default_model: str = "gpt-4o"
    llm_fallback_model: str = "claude-3-5-sonnet-20241022"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.2

    # App
    app_secret_key: str = "change-me-in-production"
    app_env: str = "development"
    log_level: str = "INFO"

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]


settings = Settings()
