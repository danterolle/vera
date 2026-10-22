import random
import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit

from vera.domain.evidence import Evidence
from vera.retrieval.resources import load_evidence_directory
from vera.training.records import fingerprint

IDENTIFIERS = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,19}|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?"
    r"|TA\d{4}|[GSM]\d{4}|A\d{2}:2021)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceGroup:
    id: str
    documents: list[Evidence]
    keys: frozenset[str]


def bundled_groups() -> tuple[list[SourceGroup], int]:
    records = load_evidence_directory("knowledge") + load_evidence_directory("corpus")
    selected = [
        item for item in records
        if not str(item.metadata.get("stix_id", "")).startswith("relationship--")
        and "Official mapped weaknesses" not in item.title
    ]
    components: list[tuple[set[str], list[Evidence]]] = []
    for item in selected:
        keys = source_keys(item)
        documents = [item]
        while True:
            remaining = []
            matched = False
            for known, members in components:
                if keys & known:
                    keys |= known
                    documents.extend(members)
                    matched = True
                else:
                    remaining.append((known, members))
            components = remaining
            if not matched:
                break
        components.append((keys, documents))
    groups = [
        SourceGroup(
            id=f"source-{fingerprint(sorted(item.id for item in documents))[:16]}",
            documents=sorted(documents, key=lambda item: item.id),
            keys=frozenset(keys),
        )
        for keys, documents in components
    ]
    return sorted(groups, key=lambda group: group.id), len(records) - len(selected)


def source_keys(document: Evidence) -> set[str]:
    identifiers = IDENTIFIERS.findall(f"{document.title} {document.content}")
    keys = {f"entity:{value.upper().split('.')[0]}" for value in identifiers}
    if document.url:
        url = urlsplit(document.url)
        keys.add(f"url:{url.netloc.lower()}{url.path.rstrip('/')}")
    keys.add(f"content:{fingerprint(document.content)}")
    return keys


def split_groups(groups: list[SourceGroup], seed: int) -> dict[str, list[SourceGroup]]:
    buckets: dict[str, list[SourceGroup]] = defaultdict(list)
    for group in groups:
        buckets[min(item.source.value for item in group.documents)].append(group)
    splits: dict[str, list[SourceGroup]] = {"train": [], "validation": [], "test": []}
    generator = random.Random(seed)
    for name in sorted(buckets):
        bucket = sorted(buckets[name], key=lambda group: group.id)
        generator.shuffle(bucket)
        held_out = max(1, len(bucket) // 10) if len(bucket) >= 3 else 0
        splits["validation"].extend(bucket[:held_out])
        splits["test"].extend(bucket[held_out:held_out * 2])
        splits["train"].extend(bucket[held_out * 2:])
    if any(not groups for groups in splits.values()):
        raise ValueError("The bundled sources cannot support three independent splits")
    return splits
