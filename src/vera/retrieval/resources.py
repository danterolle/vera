import json
from typing import Any

from vera.data import resource
from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence


def load_records(filename: str) -> list[dict[str, Any]]:
    value = json.loads(resource(filename).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{filename} must contain a JSON list")
    return value


def load_evidence(filename: str) -> list[Evidence]:
    documents: list[Evidence] = []
    for record in load_records(filename):
        documents.append(
            make_evidence(
                SourceType(record["source"]),
                record["title"],
                record["content"],
                url=record.get("url"),
                metadata=record.get("metadata", {}),
            )
        )
    return documents


def load_evidence_directory(directory: str) -> list[Evidence]:
    resources = resource(directory)
    names = sorted(
        item.name
        for item in resources.iterdir()
        if item.name.endswith(".json")
    )
    return [
        document
        for name in names
        for document in load_evidence(f"{directory}/{name}")
    ]
