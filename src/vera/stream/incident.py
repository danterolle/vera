from vera.domain.enums import Severity
from vera.domain.reports import DetectionAlert, IncidentReport, StreamStatistics

SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def build_incident(
    alerts: list[DetectionAlert],
    statistics: StreamStatistics,
) -> IncidentReport | None:
    if not alerts:
        return None
    severity = max((alert.severity for alert in alerts), key=SEVERITY_ORDER.get)
    rule_ids = {alert.rule_id for alert in alerts}
    actions = [
        "Preserve the source events and relevant host logs before containment.",
        "Validate each detection against full packet and endpoint telemetry.",
        "Scope affected assets and isolate confirmed compromised systems.",
    ]
    if "HTTP-LOG4SHELL-PATTERN" in rule_ids:
        actions.append("Verify Log4j versions and apply current vendor remediation guidance.")
    if "NET-PORT-SCAN" in rule_ids:
        actions.append("Review source ownership and block unauthorized reconnaissance traffic.")
    return IncidentReport(
        severity=severity,
        title=f"{severity.value.title()}-severity network activity",
        summary=(
            f"{len(alerts)} deterministic alert(s) were produced from "
            f"{statistics.total_events} normalized event(s). Detection does not prove compromise."
        ),
        alerts=alerts,
        statistics=statistics,
        recommended_actions=actions,
    )
