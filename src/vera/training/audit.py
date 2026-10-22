import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from vera.training.data import file_hash, read_records, verify_dataset
from vera.training.examples import TASKS
from vera.training.records import context_from_prompt, semantic_fingerprint
from vera.training.sources import bundled_groups


def audit_dataset(directory: Path) -> dict:
    manifest = verify_dataset(directory)
    groups, _ = bundled_groups()
    originals = {item.id: item for group in groups for item in group.documents}
    for first, second in combinations(manifest["splits"], 2):
        first_keys = set().union(*(
            group.keys for group in groups
            if group.id in manifest["splits"][first]["source_groups"]
        ))
        second_keys = set().union(*(
            group.keys for group in groups
            if group.id in manifest["splits"][second]["source_groups"]
        ))
        if first_keys & second_keys:
            raise ValueError("Source identifiers or URLs overlap between splits")
    seen: set[str] = set()
    report = {
        "passed": True, "human_reviewed": False,
        "dataset_sha256": file_hash(directory / "manifest.json"),
        "scope": "Automated schema, quotes, sources, duplicates, split and stream coverage checks.",
        "limitations": [
            "Not expert annotation, a legal clearance, or proof of model quality.",
            "GPU compatibility and fine-tuned quality remain unverified until Kaggle execution.",
        ],
        "splits": {},
    }
    for split in manifest["splits"]:
        records = read_records(directory, split)
        tasks: Counter[str] = Counter()
        statuses: Counter[str] = Counter()
        streams: Counter[str] = Counter()
        for record in records:
            signature = semantic_fingerprint(record)
            if signature in seen:
                raise ValueError("Semantically duplicate examples were found")
            seen.add(signature)
            if any(identifier not in originals for identifier in record.source_ids):
                raise ValueError("An example references an unknown bundled source")
            context = context_from_prompt(record.messages[1].content)
            answer = json.loads(record.messages[2].content)
            registry = {item["id"]: item for item in context["evidence"]}
            for claim in answer["claims"]:
                statuses[claim["status"]] += 1
                if claim["status"] == "supported_fact":
                    for citation in claim["citations"]:
                        evidence = registry[citation["evidence_id"]]
                        if not any(
                            originals[identifier].title == evidence["title"]
                            and originals[identifier].source.value == evidence["source"]
                            and originals[identifier].content == evidence["content"]
                            for identifier in record.source_ids
                        ):
                            raise ValueError("A factual quotation is not from a bundled source")
            tasks[record.task] += 1
            if record.task == "simulated":
                streams["with_alerts" if context["alerts"] else "without_alerts"] += 1
                payload = json.loads(context["evidence"][0]["content"])
                if payload["statistics"] != context["statistics"]:
                    raise ValueError("Stream evidence and prompt statistics disagree")
                expected_route = "FULL" if context["alerts"] else "STREAM"
                if context["route"] != expected_route:
                    raise ValueError("The synthetic stream route disagrees with its alerts")
        if set(tasks) != set(TASKS) or dict(tasks) != manifest["splits"][split]["tasks"]:
            raise ValueError("The actual task coverage does not match the manifest")
        if not streams["with_alerts"] or not streams["without_alerts"]:
            raise ValueError("Every split needs simulated traffic with and without alerts")
        if set(statuses) != {"supported_fact", "system_inference", "unavailable", "simulated"}:
            raise ValueError("A required claim status is missing")
        report["splits"][split] = {
            "examples": len(records), "tasks": dict(sorted(tasks.items())),
            "claim_statuses": dict(sorted(statuses.items())), "streams": dict(streams),
        }
    return report
