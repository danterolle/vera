from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VERA_",
        extra="ignore",
    )

    db_path: Path = Path(".vera/vera.db")
    corpus_dir: Path = Path(".vera/corpus")
    live_sources: bool = True
    request_timeout_seconds: float = Field(default=8.0, ge=1.0, le=30.0)
    source_workers: int = Field(default=5, ge=1, le=10)
    max_feed_bytes: int = Field(default=80 * 1024 * 1024, ge=1024, le=150 * 1024 * 1024)
    max_corpus_documents: int = Field(default=20_000, ge=100, le=100_000)
    nvd_api_key: SecretStr | None = None

    llm_provider: Literal["deterministic", "ollama", "openai", "gemini"] = "deterministic"
    llm_model: str = "llama3.1:8b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    max_model_calls: int = Field(default=2, ge=1, le=4)
    max_tool_calls: int = Field(default=12, ge=1, le=40)
    grounding_min_coverage: float = Field(default=0.55, ge=0.3, le=1.0)

    embedding_backend: Literal["hash", "sentence-transformers"] = "hash"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    retrieval_k: int = Field(default=5, ge=1, le=12)
    retrieval_min_score: float = Field(default=0.05, ge=0.0, le=1.0)
    memory_k: int = Field(default=3, ge=0, le=10)
    max_events: int = Field(default=10_000, ge=1, le=100_000)
    port_scan_threshold: int = Field(default=10, ge=2, le=1000)
    port_scan_window_seconds: int = Field(default=60, ge=1, le=86_400)
    auth_failure_threshold: int = Field(default=5, ge=2, le=1000)
    auth_failure_window_seconds: int = Field(default=300, ge=1, le=86_400)
    syn_burst_threshold: int = Field(default=20, ge=2, le=100_000)
    syn_burst_window_seconds: int = Field(default=10, ge=1, le=3600)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
