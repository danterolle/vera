from dataclasses import dataclass

from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import GeneratedAnswer
from vera.reasoning.grounding import grounding_error, quote_is_verbatim


@dataclass(frozen=True)
class ValidationOutcome:
    draft: GeneratedAnswer
    errors: list[str]


def validate_and_repair(
    draft: GeneratedAnswer,
    evidence: list[Evidence],
    *,
    repair: bool,
    minimum_coverage: float = 0.55,
) -> ValidationOutcome:
    by_id = {item.id: item for item in evidence}
    errors: list[str] = []
    claims: list[Claim] = []
    for index, claim in enumerate(draft.claims):
        referenced = set(claim.evidence_ids) | {
            citation.evidence_id for citation in claim.citations
        }
        missing = sorted(referenced - by_id.keys())
        cited = [by_id[item] for item in claim.evidence_ids if item in by_id]
        error = _claim_error(claim, cited, by_id, missing, minimum_coverage)
        if error:
            errors.append(f"Claim {index} ({claim.status.value}): {error}")
            claims.append(_repair_claim(claim, cited, by_id) if repair else claim)
        else:
            claims.append(claim)
    return ValidationOutcome(draft.model_copy(update={"claims": claims}), errors)


def _claim_error(
    claim: Claim,
    cited: list[Evidence],
    by_id: dict[str, Evidence],
    missing: list[str],
    minimum_coverage: float,
) -> str | None:
    if missing:
        return f"unknown evidence IDs: {', '.join(missing)}"
    citation_ids = {citation.evidence_id for citation in claim.citations}
    if not citation_ids.issubset(set(claim.evidence_ids)):
        return "citation IDs must also be listed in evidence_ids"
    for citation in claim.citations:
        if not quote_is_verbatim(citation, by_id[citation.evidence_id]):
            return (
                f"citation {citation.evidence_id} has a supporting quote "
                "that is not present verbatim"
            )
    if claim.status == ClaimStatus.SUPPORTED_FACT:
        if not claim.citations:
            return "supported fact has no verbatim supporting quotation"
        if set(claim.evidence_ids) != citation_ids:
            return "every supported-fact evidence ID requires a supporting quotation"
        for citation in claim.citations:
            item = by_id[citation.evidence_id]
            if item.status != EvidenceStatus.AVAILABLE or item.source == SourceType.MEMORY:
                return (
                    f"supported fact cites non-authoritative evidence "
                    f"{citation.evidence_id}"
                )
            error = grounding_error(claim.text, citation, item, minimum_coverage)
            if error is not None:
                return (
                    f"supported fact is not grounded by {citation.evidence_id}: {error}"
                )
    if claim.status == ClaimStatus.UNAVAILABLE and cited and not any(
        item.status == EvidenceStatus.UNAVAILABLE for item in cited
    ):
        return "unavailable claim has no unavailable-source evidence"
    if claim.status == ClaimStatus.SIMULATED and not any(
        item.status == EvidenceStatus.SIMULATED for item in cited
    ):
        return "simulated claim has no simulated evidence"
    return None


def _repair_claim(
    claim: Claim,
    cited: list[Evidence],
    by_id: dict[str, Evidence],
) -> Claim:
    valid_ids = [item.id for item in cited]
    valid_citations = [
        citation
        for citation in claim.citations
        if citation.evidence_id in by_id
        and citation.evidence_id in valid_ids
        and quote_is_verbatim(citation, by_id[citation.evidence_id])
    ]
    if any(item.status == EvidenceStatus.SIMULATED for item in cited):
        status = ClaimStatus.SIMULATED
    elif any(item.status == EvidenceStatus.UNAVAILABLE for item in cited):
        status = ClaimStatus.UNAVAILABLE
    else:
        status = ClaimStatus.SYSTEM_INFERENCE
    return claim.model_copy(
        update={
            "status": status,
            "evidence_ids": valid_ids,
            "citations": valid_citations,
        }
    )
