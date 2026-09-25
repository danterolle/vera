from vera.domain.enums import ClaimStatus, EvidenceStatus
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import ReflectionReport


def reflect(
    claims: list[Claim],
    evidence: list[Evidence],
    validation_errors: list[str],
) -> ReflectionReport:
    available_sources = sorted(
        {item.source.value for item in evidence if item.status == EvidenceStatus.AVAILABLE}
    )
    missing_sources = sorted(
        {item.source.value for item in evidence if item.status == EvidenceStatus.UNAVAILABLE}
    )
    unsupported = sum(
        claim.status == ClaimStatus.SYSTEM_INFERENCE and not claim.evidence_ids for claim in claims
    )
    factual = [claim for claim in claims if claim.status == ClaimStatus.SUPPORTED_FACT]
    supported = sum(bool(claim.evidence_ids) for claim in factual)
    base = supported / len(factual) if factual else 1.0
    penalty = min(0.5, 0.1 * len(validation_errors) + 0.05 * len(missing_sources))
    gaps = list(validation_errors)
    if missing_sources:
        gaps.append("Some selected authoritative sources were unavailable.")
    if not available_sources:
        gaps.append("No authoritative evidence was available.")
    return ReflectionReport(
        completeness_score=max(0.0, round(base - penalty, 2)),
        context_used=available_sources,
        missing_sources=missing_sources,
        unsupported_claims=unsupported,
        gaps=gaps,
    )
