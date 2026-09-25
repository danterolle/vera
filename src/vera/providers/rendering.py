from vera.domain.enums import EvidenceStatus
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import IncidentReport


def render_answer(
    summary: str,
    claims: list[Claim],
    evidence: list[Evidence],
    incident: IncidentReport | None,
) -> str:
    lines = ["## Assessment", summary]
    if incident is not None:
        lines.extend(
            [
                "",
                "## Incident",
                incident.summary,
                "",
                "### Recommended actions",
                *[f"- {action}" for action in incident.recommended_actions],
            ]
        )
    if claims:
        lines.extend(["", "## Findings"])
        for claim in claims:
            citations = " ".join(f"[{item}]" for item in claim.evidence_ids)
            lines.append(f"- **{claim.status.value}**: {claim.text} {citations}".rstrip())
    lines.extend(["", "## Sources"])
    for item in evidence:
        location = item.url or "local evidence"
        label = item.status.value
        lines.append(f"- [{item.id}] {item.title} - {location} ({label})")
    if not evidence:
        lines.append("- No evidence was available.")
    return "\n".join(lines)


def available_evidence(evidence: list[Evidence]) -> list[Evidence]:
    return [item for item in evidence if item.status == EvidenceStatus.AVAILABLE]
