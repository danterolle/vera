import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from vera.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in tuple(os.environ):
        if name.startswith("VERA_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "vera.db",
        corpus_dir=tmp_path / "corpus",
        live_sources=False,
        llm_provider="deterministic",
        embedding_backend="hash",
    )
