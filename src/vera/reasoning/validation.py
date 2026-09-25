from dataclasses import dataclass

from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import GeneratedAnswer


@dataclass(frozen=True)
class ValidationOutcome:
    draft: GeneratedAnswer
    errors: list[str]


def validate_and_repair(
    draft: GeneratedAnswer,
    evidence: list[Evidence],
    *,
    repair: bool,
) -> ValidationOutcome:
    by_id = {item.id: item for item in evidence}
    errors: list[str] = []
    claims: list[Claim] = []
    for index, claim in enumerate(draft.claims):
        cited = [by_id[item] for item in claim.evidence_ids if item in by_id]
        missing = sorted(set(claim.evidence_ids) - by_id.keys())
        error = _claim_error(claim, cited, missing)
        if error:
            errors.append(f"Claim {index}: {error}")
            claims.append(_repair_claim(claim, cited) if repair else claim)
        else:
            claims.append(claim)
    return ValidationOutcome(draft.model_copy(update={"claims": claims}), errors)


def _claim_error(claim: Claim, cited: list[Evidence], missing: list[str]) -> str | None:
    if missing:
        return f"unknown evidence IDs: {', '.join(missing)}"
    if claim.status == ClaimStatus.SUPPORTED_FACT:
        valid = any(
            item.status == EvidenceStatus.AVAILABLE and item.source != SourceType.MEMORY
            for item in cited
        )
        if not valid:
            return "supported fact has no available authoritative evidence"
    if claim.status == ClaimStatus.UNAVAILABLE and not any(
        item.status == EvidenceStatus.UNAVAILABLE for item in cited
    ):
        return "unavailable claim has no unavailable-source evidence"
    if claim.status == ClaimStatus.SIMULATED and not any(
        item.status == EvidenceStatus.SIMULATED for item in cited
    ):
        return "simulated claim has no simulated evidence"
    return None


def _repair_claim(claim: Claim, cited: list[Evidence]) -> Claim:
    valid_ids = [item.id for item in cited]
    if any(item.status == EvidenceStatus.SIMULATED for item in cited):
        status = ClaimStatus.SIMULATED
    elif any(item.status == EvidenceStatus.UNAVAILABLE for item in cited):
        status = ClaimStatus.UNAVAILABLE
    else:
        status = ClaimStatus.SYSTEM_INFERENCE
    return claim.model_copy(update={"status": status, "evidence_ids": valid_ids})
