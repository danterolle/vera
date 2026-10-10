from vera.domain.enums import Severity
from vera.domain.reports import DetectionAlert
from vera.domain.requests import NetworkEvent

SUSPICIOUS_PATHS = ("../", "/etc/passwd", "%2e%2e", "/proc/self")
COMMAND_MARKERS = (";cat ", "|sh", "$(curl", "`id`")
LOG4SHELL_MARKERS = ("${jndi:", "%24%7bjndi")
DEFINITIONS = (
    (
        LOG4SHELL_MARKERS,
        "HTTP-LOG4SHELL-PATTERN",
        "Log4Shell-style JNDI lookup pattern",
        Severity.CRITICAL,
        "T1190",
        ["CVE-2021-44228"],
        0.95,
    ),
    (
        SUSPICIOUS_PATHS,
        "HTTP-PATH-TRAVERSAL",
        "Path traversal pattern",
        Severity.HIGH,
        "T1190",
        [],
        0.9,
    ),
    (
        COMMAND_MARKERS,
        "HTTP-COMMAND-INJECTION",
        "Command injection pattern",
        Severity.HIGH,
        "T1059",
        [],
        0.85,
    ),
)


def detect_http_payloads(events: list[NetworkEvent]) -> list[DetectionAlert]:
    alerts = []
    for index, event in enumerate(events):
        uri = (event.http_uri or "").lower()
        for markers, rule_id, title, severity, technique, cves, confidence in DEFINITIONS:
            if any(marker in uri for marker in markers):
                alerts.append(
                    DetectionAlert(
                        rule_id=rule_id,
                        title=title,
                        description=f"Event {index} contains a matching HTTP URI marker.",
                        severity=severity,
                        technique_id=technique,
                        cve_ids=cves,
                        event_indexes=[index],
                        first_seen=event.timestamp,
                        last_seen=event.timestamp,
                        confidence=confidence,
                    )
                )
    return alerts
