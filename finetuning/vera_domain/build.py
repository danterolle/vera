import hashlib
import json
import random
import shutil
from collections import Counter
from pathlib import Path

from vera.providers.prompts import SYSTEM_PROMPT
from vera_domain.acquire import acquire_sources
from vera_domain.concepts import concept_scenarios, conversation_scenarios
from vera_domain.knowledge import knowledge_scenarios
from vera_domain.models import file_hash, semantic_fingerprint
from vera_domain.normalize import load_fragments
from vera_domain.partition import split_fragments
from vera_domain.traffic import traffic_scenarios

SPLITS = ("train", "validation", "test")
LIMITATIONS = [
    "Answers are mechanically source-grounded scenarios, not expert human annotations.",
    "All traffic is controlled simulation, not production telemetry.",
    "Source fragments are frozen snapshots, not live vulnerability intelligence.",
    "Social, clarification and language variants are authored templates, not observed users.",
    "Full training requires dataset review and a real Kaggle compatibility run.",
]


def write_shards(directory: Path, name: str, rows: list[dict]) -> dict[str, str]:
    hashes = {}
    for index in range(0, len(rows), 200):
        path = directory / name / f"part-{index // 200:03d}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows[index:index + 200]),
            encoding="utf-8",
        )
        hashes[str(path.relative_to(directory))] = file_hash(path)
    return hashes


def build_domain_dataset(snapshots: Path, output: Path, *, bundled: Path,
                         seed: int = 3407, card: Path | None = None) -> dict:
    if output.exists():
        raise FileExistsError(f"Choose a new domain dataset directory: {output}")
    upstream = acquire_sources(snapshots)
    fragments, source_counts = load_fragments(snapshots, bundled)
    partitions, assignments = split_fragments(fragments, seed)
    manifest = {
        "format_version": 1, "dataset_version": "v4",
        "purpose": "domain_sft_candidate", "origin": "source_grounded_synthetic",
        "human_reviewed": False, "training_authorized": False, "seed": seed,
        "response_language": "English",
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "upstream": upstream, "source_counts": source_counts,
        "bundled_corpus": {
            "files": sorted(path.name for path in bundled.glob("*.json")),
            "fragments": sum(1 for item in fragments if item.snapshot == "bundled-corpus"),
        },
        "splits": {}, "files": {}, "limitations": LIMITATIONS,
    }
    output.mkdir(parents=True)
    signatures: set[str] = set()
    source_rows = [item.model_dump(mode="json") | {"group": assignments[item.id]}
                   for item in fragments]
    manifest["files"].update(write_shards(output, "sources", source_rows))
    for number, split in enumerate(SPLITS):
        records = knowledge_scenarios(partitions[split], assignments, split, seed + number)
        records.extend(concept_scenarios(partitions[split], assignments, split, seed + number))
        records.extend(conversation_scenarios(split))
        traffic, replays = traffic_scenarios(split, seed + number)
        records.extend(traffic)
        unique, duplicates = [], Counter()
        for record in records:
            signature = semantic_fingerprint(record)
            if signature in signatures:
                duplicates[record.task] += 1
                continue
            signatures.add(signature)
            unique.append(record)
        random.Random(seed + number).shuffle(unique)
        manifest["files"].update(write_shards(
            output, split, [item.model_dump(mode="json") for item in unique],
        ))
        manifest["files"].update(write_shards(output, f"replays/{split}", replays))
        manifest["splits"][split] = {
            "examples": len(unique),
            "tasks": dict(sorted(Counter(item.task for item in unique).items())),
            "source_groups": sorted({group for record in unique for group in record.groups}),
            "entities": len({item.entity_id for item in partitions[split]}),
            "fragments": len(partitions[split]),
            "alert_counts": _counter(item.scenario.alert_count for item in unique),
            "intents": _counter(item.scenario.intent for item in unique),
            "languages": _counter(item.scenario.language for item in unique),
            "conversation_turns": _counter(item.scenario.conversation_turns for item in unique),
            "duplicate_scenarios_removed": dict(sorted(duplicates.items())),
        }
    for name in ("attack", "kev"):
        path = output / "licenses" / f"{name}-LICENSE.txt"
        path.parent.mkdir(exist_ok=True)
        shutil.copyfile(snapshots / f"{name}-LICENSE.txt", path)
        manifest["files"][str(path.relative_to(output))] = file_hash(path)
    if card is not None:
        shutil.copyfile(card, output / "DATASET.md")
        manifest["files"]["DATASET.md"] = file_hash(output / "DATASET.md")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True) + "\n")
    manifest["files"]["manifest.json"] = file_hash(output / "manifest.json")
    return manifest


def _counter(values) -> dict[str, int]:
    return {str(key): value for key, value in sorted(Counter(values).items())}
