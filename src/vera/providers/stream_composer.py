from collections import defaultdict

from vera.domain.enums import SEVERITY_ORDER, ClaimStatus, EvidenceStatus
from vera.domain.evidence import Citation, Claim, Evidence
from vera.domain.reports import DetectionAlert, StreamStatistics
from vera.domain.requests import AnalysisRequest


def compose_stream(
    request: AnalysisRequest,
    stream: Evidence | None,
    alerts: list[DetectionAlert],
    statistics: StreamStatistics,
) -> tuple[str, list[Claim]]:
    simulated = request.simulated or any(event.simulated for event in request.events)
    simulated = simulated or bool(stream and stream.status == EvidenceStatus.SIMULATED)
    status = ClaimStatus.SIMULATED if simulated else ClaimStatus.SYSTEM_INFERENCE
    if alerts:
        highest = max(alerts, key=lambda alert: SEVERITY_ORDER[alert.severity])
        summary = (
            f"Detected {len(alerts)} deterministic signal(s) across "
            f"{statistics.total_events} event(s); highest severity is "
            f"{highest.severity.value}. Detection does not prove compromise."
        )
        return summary, _alert_claims(alerts, status, stream)
    protocols = ", ".join(
        f"{name} ({count})" for name, count in statistics.protocols.items()
    ) or "none"
    summary = (
        f"Analyzed {statistics.total_events} event(s) and "
        f"{statistics.total_bytes} byte(s). No deterministic detection rule fired."
    )
    claim = _stream_claim(
        f"Observed protocols: {protocols}. No configured alert threshold was met.",
        status,
        stream,
    )
    return summary, [claim]


def _alert_claims(
    alerts: list[DetectionAlert],
    status: ClaimStatus,
    stream: Evidence | None,
) -> list[Claim]:
    groups: dict[str, list[DetectionAlert]] = defaultdict(list)
    for alert in alerts:
        groups[alert.rule_id].append(alert)
    claims = []
    for rule_id, values in sorted(groups.items()):
        first = values[0]
        confidence = max(alert.confidence for alert in values)
        text = (
            f"{first.title}: {len(values)} occurrence(s), confidence "
            f"{confidence:.0%}; rule {rule_id}. {first.description}"
        )
        claims.append(_stream_claim(text, status, stream))
    return claims


def _stream_claim(
    text: str,
    status: ClaimStatus,
    evidence: Evidence | None,
) -> Claim:
    if evidence is None:
        return Claim(text=text, status=status)
    quote = evidence.content[:4000]
    return Claim(
        text=text,
        status=status,
        evidence_ids=[evidence.id],
        citations=[Citation(evidence_id=evidence.id, supporting_quote=quote)],
    )
