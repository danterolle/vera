from collections import defaultdict

from vera.domain.enums import Severity
from vera.domain.reports import DetectionAlert
from vera.domain.requests import NetworkEvent

SUSPICIOUS_PATHS = ("../", "/etc/passwd", "%2e%2e", "/proc/self")
COMMAND_MARKERS = (";cat ", "|sh", "$(curl", "`id`")
LOG4SHELL_MARKERS = ("${jndi:", "%24%7bjndi")


def detect_events(events: list[NetworkEvent]) -> list[DetectionAlert]:
    alerts: list[DetectionAlert] = []
    alerts.extend(_detect_port_scan(events))
    alerts.extend(_detect_auth_failures(events))
    alerts.extend(_detect_syn_flood(events))
    alerts.extend(_detect_http_payloads(events))
    return alerts


def _detect_port_scan(events: list[NetworkEvent]) -> list[DetectionAlert]:
    groups: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for index, event in enumerate(events):
        if event.dst_port is not None:
            groups[(event.src_ip, event.dst_ip)].append((index, event.dst_port))
    alerts = []
    for (source, destination), samples in groups.items():
        ports = {port for _, port in samples}
        if len(ports) >= 10:
            alerts.append(
                DetectionAlert(
                    rule_id="NET-PORT-SCAN",
                    title="Probable network service discovery",
                    description=(
                        f"{source} contacted {len(ports)} distinct ports on {destination}."
                    ),
                    severity=Severity.MEDIUM,
                    technique_id="T1046",
                    event_indexes=[index for index, _ in samples],
                )
            )
    return alerts


def _detect_auth_failures(events: list[NetworkEvent]) -> list[DetectionAlert]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, event in enumerate(events):
        if event.http_status in {401, 403}:
            groups[(event.src_ip, event.dst_ip)].append(index)
    return [
        DetectionAlert(
            rule_id="HTTP-AUTH-FAILURES",
            title="Repeated HTTP authentication failures",
            description=f"{source} generated {len(indexes)} denied requests to {destination}.",
            severity=Severity.MEDIUM,
            technique_id="T1110",
            event_indexes=indexes,
        )
        for (source, destination), indexes in groups.items()
        if len(indexes) >= 5
    ]


def _detect_syn_flood(events: list[NetworkEvent]) -> list[DetectionAlert]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, event in enumerate(events):
        flags = (event.tcp_flags or "").upper()
        if "S" in flags and "A" not in flags:
            groups[(event.src_ip, event.dst_ip)].append(index)
    return [
        DetectionAlert(
            rule_id="TCP-SYN-BURST",
            title="High-volume TCP SYN activity",
            description=f"{source} sent {len(indexes)} SYN packets to {destination}.",
            severity=Severity.HIGH,
            technique_id="T1498",
            event_indexes=indexes,
        )
        for (source, destination), indexes in groups.items()
        if len(indexes) >= 20
    ]


def _detect_http_payloads(events: list[NetworkEvent]) -> list[DetectionAlert]:
    alerts: list[DetectionAlert] = []
    for index, event in enumerate(events):
        uri = (event.http_uri or "").lower()
        if any(marker in uri for marker in LOG4SHELL_MARKERS):
            alerts.append(
                DetectionAlert(
                    rule_id="HTTP-LOG4SHELL-PATTERN",
                    title="Log4Shell-style JNDI lookup pattern",
                    description=f"Event {index} contains a JNDI lookup marker in the HTTP URI.",
                    severity=Severity.CRITICAL,
                    technique_id="T1190",
                    cve_ids=["CVE-2021-44228"],
                    event_indexes=[index],
                )
            )
        if any(marker in uri for marker in SUSPICIOUS_PATHS):
            alerts.append(
                DetectionAlert(
                    rule_id="HTTP-PATH-TRAVERSAL",
                    title="Path traversal pattern",
                    description=f"Event {index} contains a path traversal marker.",
                    severity=Severity.HIGH,
                    technique_id="T1190",
                    event_indexes=[index],
                )
            )
        if any(marker in uri for marker in COMMAND_MARKERS):
            alerts.append(
                DetectionAlert(
                    rule_id="HTTP-COMMAND-INJECTION",
                    title="Command injection pattern",
                    description=f"Event {index} contains a command execution marker.",
                    severity=Severity.HIGH,
                    technique_id="T1059",
                    event_indexes=[index],
                )
            )
    return alerts
