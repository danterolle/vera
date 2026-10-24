import re

from vera.domain.enums import ClaimStatus, EvidenceStatus, Severity, SourceType
from vera.domain.state import GraphState
from vera.retrieval.cve import extract_cve_ids

CYBER_INTENT = re.compile(
    r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?|ATT&CK|cybersecurity|"
    r"vulnerabilit(?:y|ies)|malware|ransomware|phishing|firewall|"
    r"exploit(?:ation)?|authentication|security|injection|attack)\b",
    re.IGNORECASE,
)


def review_reasons(state: GraphState) -> list[str]:
    if state["resource_plan"].intent in {"social", "out_of_scope", "clarification"}:
        return []
    reasons = []
    alerts = [
        alert for alert in state["alerts"]
        if alert.severity in {Severity.HIGH, Severity.CRITICAL}
    ]
    if alerts:
        reasons.append(f"{len(alerts)} high or critical detection alert(s) require review.")

    reflection = state["reflection"]
    if reflection.unsupported_claims:
        reasons.append(f"{reflection.unsupported_claims} claim(s) lack verified support.")
    draft = state["draft"]
    query = state["request"].query
    cve_ids = extract_cve_ids(query)
    if draft.out_of_scope:
        if cve_ids or CYBER_INTENT.search(query) or state["alerts"]:
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
        ):
            reasons.append(f"No available evidence concerns {cve_id}.")
    if draft.claims and all(
        claim.status in {ClaimStatus.UNAVAILABLE, ClaimStatus.SYSTEM_INFERENCE}
        for claim in draft.claims
    ) and not reflection.unsupported_claims:
        reasons.append("The draft has no supported or observed findings.")
    return reasons
