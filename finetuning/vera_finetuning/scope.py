"""Cases and runtime settings for the local scope over-refusal probe."""

import json
from pathlib import Path

from vera.config import Settings

CASES = tuple(json.loads(
    Path(__file__).with_name("scope_cases.json").read_text(encoding="utf-8")
))


def settings_for(
    model: str, url: str, directory: Path, backend: str = "hash",
) -> Settings:
    return Settings(_env_file=None).model_copy(update={
        "llm_provider": "openai",
        "llm_model": model,
        "llm_base_url": f"{url}/v1",
        "llm_api_key": None,
        "llm_response_format": "json_schema",
        "llm_reasoning_effort": None,
        "llm_timeout_seconds": 300,
        "llm_max_output_tokens": 4096,
        "max_model_calls": 4,
        "live_sources": False,
        "web_search_enabled": False,
        "kg_enabled": False,
        "react_enabled": False,
        "memory_k": 0,
        "response_language": "English",
        "embedding_backend": backend,
        "db_path": directory / "probe.db",
        "corpus_dir": directory / "corpus",
    })
