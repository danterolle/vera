from vera.domain.enums import ClaimStatus, EvidenceStatus
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import ReflectionReport


def _is_grounding_error(error: str) -> bool:
    return any(
        marker in error
        for marker in ("supported fact", "supported-fact", "supporting quote")
    )


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
    inference_count = sum(claim.status == ClaimStatus.SYSTEM_INFERENCE for claim in claims)
    grounding_failures = sum(
        _is_grounding_error(error)
        for error in validation_errors
    )
    factual_failures = sum("(supported_fact)" in error for error in validation_errors)
    hidden_failures = max(0, grounding_failures - inference_count)
    unsupported = inference_count + hidden_failures
    factual = [claim for claim in claims if claim.status == ClaimStatus.SUPPORTED_FACT]
    assessable = [
        claim
        for claim in claims
        if claim.status in {ClaimStatus.SUPPORTED_FACT, ClaimStatus.SYSTEM_INFERENCE}
    ]
    denominator = len(assessable) + hidden_failures
    base = len(factual) / denominator if denominator else 1.0
    non_grounding_errors = max(0, len(validation_errors) - grounding_failures)
    penalty = min(0.5, 0.1 * non_grounding_errors + 0.05 * len(missing_sources))
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
        validation_failures=len(validation_errors),
        factual_validation_failures=factual_failures,
        grounding_failures=grounding_failures,
        gaps=gaps,
    )
