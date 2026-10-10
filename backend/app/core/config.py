"""Application configuration – environment-driven for Docker / Kubernetes."""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Aether Assistant"
    app_version: str = "0.2.0"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048

    langchain_tracing_v2: bool = False
    langchain_api_key: Optional[str] = None
    langchain_project: str = "aether-assistant"

    pinecone_api_key: Optional[str] = None
    pinecone_index: str = "aether-knowledge"
    use_pinecone: bool = False
    hybrid_alpha: float = 0.6
    mock_docs_path: str = "/app/data/mock_docs"

    auth_mode: str = "local"  # local | keycloak
    jwt_secret: str = "aether-poc-change-me-in-production-use-32chars-min"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    enable_auth: bool = True

    keycloak_url: str = "http://keycloak:8080"
    keycloak_realm: str = "aether"
    keycloak_client_id: str = "aether-api"
    keycloak_client_secret: Optional[str] = None
    keycloak_audience: str = "account"
    keycloak_public_url: str = "http://localhost:8080"

    database_url: str = "postgresql+asyncpg://aether:aether@postgres:5432/aether"
    database_echo: bool = False

    redis_url: str = "redis://redis:6379/0"
    redis_session_ttl_seconds: int = 604800

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    cors_origins: List[str] = [
        "http://localhost:4200",
        "http://localhost:3000",
        "http://localhost",
        "*",
    ]

    company_name: str = "Aether Bank"
    assistant_name: str = "Aether Assistant"


@lru_cache
def get_settings() -> Settings:
    return Settings()
