from vera.domain.enums import ClaimStatus, EvidenceStatus, Severity, SourceType
from vera.domain.state import GraphState
from vera.retrieval.cve import extract_cve_ids


def review_reasons(state: GraphState) -> list[str]:
    reasons = []
    if state.get("provider_fallback"):
        reasons.append("Model generation failed or exhausted its budget; fallback requires review.")
    reasons.extend(state.get("summary_errors", []))
    intent = state["resource_plan"].intent
    draft = state["draft"]
    cve_ids = extract_cve_ids(state["request"].query)
    if (
        intent != "cybersecurity"
        and not cve_ids
        and not state["alerts"]
        and not state["reflection"].validation_failures
        and not state["reflection"].unsupported_claims
    ):
        if draft.claims or draft.out_of_scope != (intent == "out_of_scope"):
            reasons.append("The draft does not match the conversational intent.")
        return reasons
    alerts = [
        alert for alert in state["alerts"]
        if alert.severity in {Severity.HIGH, Severity.CRITICAL}
    ]
    if alerts:
        reasons.append(f"{len(alerts)} high or critical detection alert(s) require review.")

    reflection = state["reflection"]
    if reflection.unsupported_claims:
        reasons.append(f"{reflection.unsupported_claims} claim(s) lack verified support.")
    elif reflection.validation_failures:
        reasons.append(f"{reflection.validation_failures} claim(s) failed citation validation.")
    if draft.out_of_scope:
        if intent == "cybersecurity" or cve_ids or state["alerts"]:
            reasons.append("A cybersecurity request was classified as out of scope.")
        return reasons

    if not draft.claims:
        reasons.append("The draft contains no findings to assess.")
    usable = [
        item for item in state["evidence"]
        if item.source != SourceType.MEMORY and (
            item.status == EvidenceStatus.AVAILABLE
            or item.source == SourceType.STREAM and item.status == EvidenceStatus.SIMULATED
        )
    ]
    if not usable:
        reasons.append("No usable non-memory evidence supports the analysis.")
    for cve_id in cve_ids:
        if not any(
            cve_id in item.title.upper() or item.metadata.get("cve_id") == cve_id
            for item in usable
        ) and not _cve_acknowledged(state, cve_id):
            reasons.append(f"No available evidence concerns {cve_id}.")
    if (
        draft.claims
        and all(
            claim.status in {ClaimStatus.UNAVAILABLE, ClaimStatus.SYSTEM_INFERENCE}
            for claim in draft.claims
        )
        and not reflection.unsupported_claims
        and not _all_unavailable_acknowledged(state)
    ):
        reasons.append("The draft has no supported or observed findings.")
    return reasons


def _cve_acknowledged(state: GraphState, cve_id: str) -> bool:
    """A correct 'missing' answer does not need review just because evidence is absent."""
    if not any(
        claim.status == ClaimStatus.UNAVAILABLE for claim in state["draft"].claims
    ):
        return False
    return any(
        item.status == EvidenceStatus.UNAVAILABLE
        and (
            cve_id in item.title.upper()
            or item.metadata.get("cve_id") == cve_id
        )
        for item in state["evidence"]
    )


def _all_unavailable_acknowledged(state: GraphState) -> bool:
    draft = state["draft"]
    return bool(draft.claims) and all(
        claim.status == ClaimStatus.UNAVAILABLE for claim in draft.claims
    ) and any(item.status == EvidenceStatus.UNAVAILABLE for item in state["evidence"])
