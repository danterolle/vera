from vera.domain.enums import EvidenceStatus
from vera.domain.evidence import Evidence

PROVENANCE_PRIORITY = {
    "live_api": 3,
    "synchronized_feed": 2,
    "bundled_snapshot": 1,
}


def deduplicate_evidence(evidence: list[Evidence]) -> list[Evidence]:
    best: dict[tuple[str, str], Evidence] = {}
    for item in evidence:
        key = _record_key(item)
        if key is None or item.status != EvidenceStatus.AVAILABLE:
            continue
        existing = best.get(key)
        if existing is None or _priority(item) > _priority(existing):
            best[key] = item
    result = []
    emitted_keys = set()
    emitted_ids = set()
    for item in evidence:
        key = _record_key(item)
        if key is not None and item.status == EvidenceStatus.AVAILABLE:
            if key in emitted_keys:
                continue
            item = best[key]
            emitted_keys.add(key)
        if item.id not in emitted_ids:
            result.append(item)
            emitted_ids.add(item.id)
    return result


def _record_key(evidence: Evidence) -> tuple[str, str] | None:
    cve_id = evidence.metadata.get("cve_id")
    if cve_id:
        return evidence.source.value, str(cve_id)
    external_id = evidence.metadata.get("external_id")
    if external_id and "—" not in evidence.title and not evidence.metadata.get("graph_relations"):
        return evidence.source.value, str(external_id)
    return None


def _priority(evidence: Evidence) -> tuple[int, float]:
    provenance = evidence.metadata.get("provenance")
    if evidence.metadata.get("kg_record_key") and provenance == "live_api":
        provenance = "cached_api"
    if evidence.metadata.get("snapshot", False):
        provenance = "bundled_snapshot"
    return (
        PROVENANCE_PRIORITY.get(str(provenance), 2),
        evidence.retrieved_at.timestamp(),
    )
