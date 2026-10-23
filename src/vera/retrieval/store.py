from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from vera.domain.evidence import Evidence
from vera.errors import ConfigurationError
from vera.retrieval.models import CorpusFeed, FeedBatch, FeedManifest


class CorpusStore:
    def __init__(self, directory: Path, max_documents: int) -> None:
        self.directory = directory
        self.max_documents = max_documents

    def load(self) -> list[Evidence]:
        if not self.directory.exists():
            return []
        documents: list[Evidence] = []
        for path in sorted(self.directory.glob("*.jsonl")):
            documents.extend(self._load_file(path))
            if len(documents) > self.max_documents:
                raise ConfigurationError(
                    f"Synchronized corpus exceeds {self.max_documents} documents"
                )
        return documents

    def manifests(self) -> list[FeedManifest]:
        if not self.directory.exists():
            return []
        manifests = []
        for path in sorted(self.directory.glob("*.manifest.json")):
            try:
                manifests.append(FeedManifest.model_validate_json(path.read_text()))
            except (OSError, ValidationError) as exc:
                raise ConfigurationError(f"Invalid corpus manifest {path}: {exc}") from exc
        return manifests

    def replace(self, batches: list[FeedBatch]) -> None:
        replaced = {f"{batch.manifest.feed.value}.jsonl" for batch in batches}
        existing = sum(
            len(self._load_file(path))
            for path in self.directory.glob("*.jsonl")
            if path.name not in replaced
        ) if self.directory.exists() else 0
        total = existing + sum(len(batch.evidence) for batch in batches)
        if total > self.max_documents:
            raise ConfigurationError(
                f"Synchronization produced {total} documents; limit is {self.max_documents}"
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        staged: list[tuple[Path, Path]] = []
        try:
            for batch in batches:
                data_path = self._path(batch.manifest.feed, ".jsonl")
                manifest_path = self._path(batch.manifest.feed, ".manifest.json")
                token = uuid4().hex
                data_temp = data_path.with_name(f".{data_path.name}.{token}.tmp")
                manifest_temp = manifest_path.with_name(
                    f".{manifest_path.name}.{token}.tmp"
                )
                staged.extend([(data_temp, data_path), (manifest_temp, manifest_path)])
                data = "\n".join(item.model_dump_json() for item in batch.evidence) + "\n"
                data_temp.write_text(data, encoding="utf-8")
                manifest_temp.write_text(batch.manifest.model_dump_json(indent=2), encoding="utf-8")
            for temporary, target in staged:
                temporary.replace(target)
        except OSError as exc:
            raise ConfigurationError(f"Cannot update synchronized corpus: {exc}") from exc
        finally:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)

    def _load_file(self, path: Path) -> list[Evidence]:
        documents = []
        try:
            lines = path.read_text().splitlines()
        except OSError as exc:
            raise ConfigurationError(f"Cannot read synchronized corpus {path}: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if line.strip():
                try:
                    documents.append(Evidence.model_validate_json(line))
                except ValidationError as exc:
                    raise ConfigurationError(
                        f"Invalid synchronized corpus {path} at line {line_number}: {exc}"
                    ) from exc
        return documents

    def _path(self, feed: CorpusFeed, suffix: str) -> Path:
        if feed == CorpusFeed.ALL:
            raise ConfigurationError("'all' is not a persistable corpus feed")
        return self.directory / f"{feed.value}{suffix}"
