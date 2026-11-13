from collections.abc import Sequence

from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.evidence import Claim, Evidence
from vera.retrieval.subjects import mentions_subject

NON_KNOWLEDGE = {SourceType.MEMORY, SourceType.STREAM}


def knowledge_evidence(evidence: Sequence[Evidence]) -> list[Evidence]:
    return [
        item for item in evidence
        if item.source not in NON_KNOWLEDGE
        and item.status == EvidenceStatus.AVAILABLE
        and not item.metadata.get("fallback", False)
    ]


def has_relevant_evidence(
    evidence: Sequence[Evidence], subjects: Sequence[str],
) -> bool:
    """True when at least one supplied record names the question's subject."""
    if not subjects:
        return True
    return any(
        mentions_subject(item, subject)
        for item in knowledge_evidence(evidence)
        for subject in subjects
    )


def unrelated_supported_claims(
    claims: Sequence[Claim],
    evidence: Sequence[Evidence],
    subjects: Sequence[str],
) -> list[int]:
    """Indexes of supported facts that cite knowledge while no record is on topic."""
    if not subjects or has_relevant_evidence(evidence, subjects):
        return []
    by_id = {item.id: item for item in evidence}
    unrelated = []
    for index, claim in enumerate(claims):
        if claim.status != ClaimStatus.SUPPORTED_FACT:
            continue
        cited = [
            by_id[item]
            for item in claim.evidence_ids
            if item in by_id and by_id[item].source not in NON_KNOWLEDGE
        ]
        if cited:
            unrelated.append(index)
    return unrelated
