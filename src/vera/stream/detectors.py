from collections import Counter, deque

from vera.domain.enums import Severity
from vera.domain.reports import DetectionAlert
from vera.domain.requests import NetworkEvent
from vera.stream.http_detection import detect_http_payloads
from vera.stream.policy import DetectionPolicy
from vera.stream.windowing import (
    IndexedEvent,
    first_window,
    group_events,
    trim_window,
    window_alert,
)


def detect_events(
    events: list[NetworkEvent],
    policy: DetectionPolicy | None = None,
) -> list[DetectionAlert]:
    selected = policy or DetectionPolicy()
    return [
        *_detect_port_scan(events, selected),
        *_detect_auth_failures(events, selected),
        *_detect_syn_flood(events, selected),
        *detect_http_payloads(events),
    ]


def _detect_port_scan(
    events: list[NetworkEvent],
    policy: DetectionPolicy,
) -> list[DetectionAlert]:
    groups = group_events(events, lambda event: event.dst_port is not None)
    alerts = []
    for (source, destination), samples in groups.items():
        window: deque[IndexedEvent] = deque()
        ports: Counter[int] = Counter()
        for sample in samples:
            trim_window(window, sample[1], policy.port_scan_window_seconds, ports)
            window.append(sample)
            ports[sample[1].dst_port] += 1
            if len(ports) < policy.port_scan_threshold:
                continue
            selected = list(window)
            alerts.append(
                window_alert(
                    selected,
                    rule_id="NET-PORT-SCAN",
                    title="Probable network service discovery",
                    description=(
                        f"{source} contacted {len(ports)} distinct ports on {destination} "
                        f"within {policy.port_scan_window_seconds} seconds."
                    ),
                    severity=Severity.MEDIUM,
                    technique_id="T1046",
                    observed_count=len(ports),
                    threshold=policy.port_scan_threshold,
                    window_seconds=policy.port_scan_window_seconds,
                    confidence=0.8,
                )
            )
            break
    return alerts


def _detect_auth_failures(
    events: list[NetworkEvent],
    policy: DetectionPolicy,
) -> list[DetectionAlert]:
    groups = group_events(events, lambda event: event.http_status in {401, 403})
    return [
        window_alert(
            selected,
            rule_id="HTTP-AUTH-FAILURES",
            title="Repeated HTTP authentication failures",
            description=(
                f"{source} generated {len(selected)} denied requests to {destination} "
                f"within {policy.auth_failure_window_seconds} seconds."
            ),
            severity=Severity.MEDIUM,
            technique_id="T1110",
            observed_count=len(selected),
            threshold=policy.auth_failure_threshold,
            window_seconds=policy.auth_failure_window_seconds,
            confidence=0.75,
        )
        for (source, destination), samples in groups.items()
        if (
            selected := first_window(
                samples,
                policy.auth_failure_threshold,
                policy.auth_failure_window_seconds,
            )
        )
    ]


def _detect_syn_flood(
    events: list[NetworkEvent],
    policy: DetectionPolicy,
) -> list[DetectionAlert]:
    groups = group_events(
        events,
        lambda event: "S" in (event.tcp_flags or "").upper()
        and "A" not in (event.tcp_flags or "").upper(),
    )
    return [
        window_alert(
            selected,
            rule_id="TCP-SYN-BURST",
            title="High-volume TCP SYN activity",
            description=(
                f"{source} sent {len(selected)} SYN packets to {destination} "
                f"within {policy.syn_burst_window_seconds} seconds."
            ),
            severity=Severity.HIGH,
            technique_id="T1498",
            observed_count=len(selected),
            threshold=policy.syn_burst_threshold,
            window_seconds=policy.syn_burst_window_seconds,
            confidence=0.85,
        )
        for (source, destination), samples in groups.items()
        if (
            selected := first_window(
                samples,
                policy.syn_burst_threshold,
                policy.syn_burst_window_seconds,
            )
        )
    ]
