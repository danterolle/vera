from pathlib import Path

import pytest

from vera.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "vera.db",
        corpus_dir=tmp_path / "corpus",
        live_sources=False,
        llm_provider="deterministic",
        embedding_backend="hash",
    )
