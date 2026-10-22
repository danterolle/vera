import json
import random
from collections import Counter
from pathlib import Path

from vera.providers.prompts import SYSTEM_PROMPT
from vera.training.examples import TASKS, make_record
from vera.training.records import TrainingRecord, fingerprint, semantic_fingerprint
from vera.training.sources import bundled_groups, split_groups

DEFAULT_COUNTS = {"train": 2000, "validation": 200, "test": 300}


def build_dataset(
    destination: Path, *, seed: int = 3407, counts: dict[str, int] | None = None,
) -> dict:
    requested = DEFAULT_COUNTS if counts is None else counts
    if set(requested) != set(DEFAULT_COUNTS) or any(count < 20 for count in requested.values()):
        raise ValueError("Provide train, validation and test sizes of at least 20 examples")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Dataset output must be empty: {destination}")
    groups, excluded = bundled_groups()
    splits = split_groups(groups, seed)
    manifest = {
        "format_version": 1,
        "seed": seed,
        "system_prompt_sha256": fingerprint(SYSTEM_PROMPT),
        "origin": "synthetic_template",
        "human_reviewed": False,
        "license": "Upstream source terms apply; review before upload or redistribution.",
        "limitations": [
            "Template augmentation is not a collection of independent expert annotations.",
            "Only bundled single-entity records are used; relationship-only records are excluded.",
            "No private logs, runtime databases, live downloads or human HITL decisions are read.",
            "Stream families are held out separately; their technique IDs may occur in documents.",
            "Scope examples and synthetic revisions are not human review decisions.",
        ],
        "excluded_relationship_records": excluded,
        "splits": {},
        "files": {},
    }
    seen: set[str] = set()
    for offset, (split, count) in enumerate(requested.items()):
        generator = random.Random(seed + offset)
        records: list[TrainingRecord] = []
        attempts = 0
        while len(records) < count:
            task = TASKS[len(records) % len(TASKS)]
            record = make_record(
                splits[split], split, task, generator,
                benign=len(records) % len(TASKS) == 14,
            )
            attempts += 1
            if attempts > count * 30:
                raise ValueError(f"Not enough unique examples for split {split}")
            signature = semantic_fingerprint(record)
            if signature not in seen:
                records.append(record)
                seen.add(signature)
        generator.shuffle(records)
        for start in range(0, count, 200):
            path = destination / split / f"part-{start // 200:03d}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(
                    json.dumps(record.model_dump(), ensure_ascii=True) + "\n"
                    for record in records[start:start + 200]
                ),
                encoding="utf-8",
            )
            manifest["files"][str(path.relative_to(destination))] = _file_hash(path)
        manifest["splits"][split] = {
            "examples": count,
            "tasks": dict(sorted(Counter(record.task for record in records).items())),
            "source_groups": sorted(group.id for group in splits[split]),
            "documents": sum(len(group.documents) for group in splits[split]),
        }
    sources = [
        {
            "id": item.id, "group": group.id, "title": item.title, "source": item.source.value,
            "url": item.url, "content_sha256": fingerprint(item.content),
            "version": {key: value for key, value in item.metadata.items()
                        if "version" in key or "date" in key},
        }
        for group in groups for item in group.documents
    ]
    path = destination / "sources.jsonl"
    path.write_text("".join(json.dumps(item, ensure_ascii=True) + "\n" for item in sources))
    manifest["files"]["sources.jsonl"] = _file_hash(path)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )
    return manifest


def _file_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
