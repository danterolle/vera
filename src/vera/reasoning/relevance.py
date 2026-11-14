from collections.abc import Sequence

from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import DetectionAlert
from vera.retrieval.subjects import IDENTIFIERS, mentions_subject, subject_candidates

NON_KNOWLEDGE = {SourceType.MEMORY, SourceType.STREAM}


def analysis_subjects(
    query: str, alerts: Sequence[DetectionAlert] = (), *,
    resolved_query: str | None = None, current_subject: str | None = None,
) -> list[str]:
    subjects = IDENTIFIERS.findall(query) or subject_candidates(
        resolved_query or query, current_subject,
    )
    for alert in alerts:
        subjects.extend(alert.cve_ids)
        if alert.technique_id:
            subjects.append(alert.technique_id)
    return list(dict.fromkeys(subjects))


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


def relevant_record_ids(evidence: Sequence[Evidence], subjects: Sequence[str]) -> set[str]:
    records = knowledge_evidence(evidence)
    if not subjects:
        return {item.id for item in records}
    direct = {item.id for item in records if has_relevant_evidence([item], subjects)}
    if not direct:
        return set()
    # A relationship may supplement a subject's own record, never replace its definition.
    return direct | {
        item.id for item in records
        if "—" in item.title and has_relevant_evidence(
            [item.model_copy(update={"title": item.title.replace("—", " ")})], subjects,
        )
    }


def unrelated_supported_claims(
    claims: Sequence[Claim],
    evidence: Sequence[Evidence],
    subjects: Sequence[str],
) -> list[int]:
    """Check each cited record; one relevant document cannot license a distractor."""
    if not subjects:
        return []
    by_id = {item.id: item for item in evidence}
    relevant = relevant_record_ids(evidence, subjects)
    unrelated = []
    for index, claim in enumerate(claims):
        if claim.status != ClaimStatus.SUPPORTED_FACT:
            continue
        cited = [
            by_id[item]
            for item in set(claim.evidence_ids) | {
                citation.evidence_id for citation in claim.citations
            }
            if item in by_id and by_id[item].source not in NON_KNOWLEDGE
        ]
        if any(item.id not in relevant for item in cited):
            unrelated.append(index)
    return unrelated
