import random
import re
from collections import defaultdict

from vera_domain.models import SourceFragment, fingerprint


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def shingles(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return {tuple(words[index:index + 5]) for index in range(max(0, len(words) - 4))}


def first_sentence(text: str) -> str:
    match = re.search(r"[.!?](?:\s|$)", text)
    return text[: match.start() + 1] if match else text


def split_fragments(
    fragments: list[SourceFragment], seed: int,
) -> tuple[dict[str, list[SourceFragment]], dict[str, str]]:
    parents = {item.id: item.id for item in fragments}

    def find(identifier: str) -> str:
        while parents[identifier] != identifier:
            parents[identifier] = parents[parents[identifier]]
            identifier = parents[identifier]
        return identifier

    owners = {}
    inverted: dict[tuple[str, ...], set[str]] = defaultdict(set)
    signatures: dict[str, set[tuple[str, ...]]] = {}
    for item in sorted(fragments, key=lambda value: value.id):
        for key in (
            f"entity:{item.entity_id}", f"family:{item.family}",
            f"quote:{normalized_text(item.content)}",
            f"prefix:{normalized_text(item.content)[:360]}",
            f"sentence:{first_sentence(normalized_text(item.content))}",
        ):
            if key in owners:
                parents[find(item.id)] = find(owners[key])
            else:
                owners[key] = item.id
        signature = shingles(item.content)
        candidates = {identifier for token in signature for identifier in inverted[token]}
        for identifier in candidates:
            previous = signatures[identifier]
            if signature and len(signature & previous) / len(signature | previous) >= 0.85:
                parents[find(item.id)] = find(identifier)
        signatures[item.id] = signature
        for token in signature:
            inverted[token].add(item.id)
    components: dict[str, list[SourceFragment]] = defaultdict(list)
    for item in fragments:
        components[find(item.id)].append(item)
    buckets: dict[str, list[list[SourceFragment]]] = defaultdict(list)
    for items in components.values():
        buckets[min(item.source.value for item in items)].append(items)
    result = {"train": [], "validation": [], "test": []}
    assignments = {}
    generator = random.Random(seed)
    for source in sorted(buckets):
        groups = sorted(buckets[source], key=lambda items: sorted(item.id for item in items))
        generator.shuffle(groups)
        target = sum(len(items) for items in groups)
        counts = dict.fromkeys(result, 0)
        for items in sorted(groups, key=len, reverse=True):
            split = min(
                result,
                key=lambda name: counts[name] / (target * (0.8 if name == "train" else 0.1)),
            )
            identifier = f"domain-{fingerprint(sorted(item.id for item in items))[:20]}"
            counts[split] += len(items)
            result[split].extend(items)
            assignments.update({item.id: identifier for item in items})
    if any(not items for items in result.values()):
        raise ValueError("Insufficient independent source families for three splits")
    return result, assignments
