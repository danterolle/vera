import random
from datetime import UTC, datetime, timedelta

from vera.domain.enums import ClaimStatus, EvidenceStatus, Route, SourceType
from vera.domain.evidence import Citation, Claim, make_evidence
from vera.domain.requests import NetworkEvent
from vera.stream.detectors import detect_events
from vera.stream.evidence import summarize_stream
from vera.stream.statistics import calculate_statistics
from vera_domain.compose import Scenario, compose
from vera_domain.models import fingerprint

TRAVERSAL = "/../../etc/passwd"
INJECTION = "/index.php?cmd=;cat /etc/shadow"

# Each profile builds one controlled replay and declares the exact rules it must trigger.
# Cases are grouped so a split never shares a replay group with another split.
CASES = {
    "train": (
        "benign", "port_scan", "authentication", "syn_burst", "http_payload",
        "scan_and_auth", "correlated_scan_payload", "scan_and_payload",
        "triple_independent", "triple_correlated",
    ),
    "validation": (
        "benign", "port_scan", "scan_and_auth", "correlated_scan_payload",
        "triple_independent",
    ),
    "test": (
        "benign", "syn_burst", "http_payload", "scan_and_payload",
        "triple_correlated",
    ),
}
EXPECTED = {
    "benign": (),
    "port_scan": ("NET-PORT-SCAN",),
    "authentication": ("HTTP-AUTH-FAILURES",),
    "syn_burst": ("TCP-SYN-BURST",),
    "http_payload": ("HTTP-PATH-TRAVERSAL",),
    "scan_and_auth": ("NET-PORT-SCAN", "HTTP-AUTH-FAILURES"),
    "correlated_scan_payload": ("NET-PORT-SCAN", "HTTP-COMMAND-INJECTION"),
    "scan_and_payload": ("NET-PORT-SCAN", "HTTP-COMMAND-INJECTION"),
    "triple_independent": (
        "HTTP-AUTH-FAILURES", "HTTP-PATH-TRAVERSAL", "HTTP-COMMAND-INJECTION",
    ),
    "triple_correlated": (
        "HTTP-AUTH-FAILURES", "HTTP-PATH-TRAVERSAL", "HTTP-COMMAND-INJECTION",
    ),
}


def traffic_scenarios(split: str, seed: int) -> tuple[list, list[dict]]:
    generator = random.Random(seed + 31)
    records = []
    replays = []
    for case in CASES[split]:
        limit = 10 if split == "train" else 6
        for profile in range(limit):
            events = _build(case, split, profile, generator)
            alerts = detect_events(events)
            rules = tuple(sorted(alert.rule_id for alert in alerts))
            if rules != tuple(sorted(EXPECTED[case])):
                raise ValueError(f"Unexpected detector result: {case}/{split}/{profile}: {rules}")
            statistics = calculate_statistics(events)
            content, metadata = summarize_stream(statistics, alerts)
            evidence = make_evidence(
                SourceType.STREAM,
                "Normalized event-stream analysis | synthetic replay",
                content,
                status=EvidenceStatus.SIMULATED,
                metadata=metadata,
            )
            payload = [event.model_dump(mode="json") for event in events]
            replay_id = fingerprint(payload)
            group = f"replay:{split}:{case}"
            summary = _summary(case, alerts)
            claims = [
                Claim(
                    text=alert.description, status=ClaimStatus.SIMULATED,
                    evidence_ids=[evidence.id], citations=[Citation(
                        evidence_id=evidence.id,
                        supporting_quote=(
                            f'"rule_id": "{alert.rule_id}", "severity": "{alert.severity.value}"'
                        ),
                    )],
                )
                for alert in alerts
            ] or [Claim(
                text=f"No configured detection threshold was met across {len(events)} events.",
                status=ClaimStatus.SIMULATED, evidence_ids=[evidence.id],
                citations=[Citation(
                    evidence_id=evidence.id, supporting_quote='"alert_summaries": []',
                )],
            )]
            scenario = Scenario(
                task="stream_triage",
                query=(
                    f"Review the supplied {len(events)}-event lab replay for "
                    f"{case.replace('_', ' ')}. Distinguish observed signals, "
                    "detector limits and proof of compromise."
                ),
                summary=summary, evidence=[evidence], claims=claims, entities=[],
                bindings={}, route=Route.FULL if alerts else Route.STREAM,
            )
            records.append(compose(
                scenario, {}, alerts=alerts, statistics=statistics,
                detector_family=case, window_case=split,
                event_replay_id=replay_id, extra_groups=(group,),
            ))
            replays.append({
                "id": replay_id, "split": split, "family": case,
                "expected_rules": list(rules), "events": payload,
            })
    return records, replays


def _summary(case: str, alerts) -> str:
    if not alerts:
        return (
            "No configured detector fired in this simulated replay. That is not proof "
            "that the environment is safe, and egress or encrypted traffic may be uninspected."
        )
    rules = ", ".join(sorted({alert.rule_id for alert in alerts}))
    correlated = "correlated_" in case or case == "triple_correlated"
    extra = (
        " The signals share a source address, which supports correlation but not attribution."
        if correlated else ""
    )
    return (
        f"The simulated replay triggered {len(alerts)} deterministic signal(s) ({rules}). "
        f"An alert is a hypothesis about observed traffic, not proof of compromise.{extra}"
    )


def _build(case: str, split: str, profile: int, generator: random.Random) -> list[NetworkEvent]:
    origin = {"train": 10, "validation": 40, "test": 80}[split]
    start = datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=origin + profile)
    source = f"192.0.2.{origin + profile + 1}"
    target = f"198.51.100.{origin + profile + 1}"
    events: list[NetworkEvent] = []
    if case == "benign":
        events.extend(_http(source, target, start, 200, None, 6))
    elif case == "port_scan":
        events.extend(_scan(source, target, start, generator))
    elif case == "authentication":
        events.extend(_auth(source, target, start))
    elif case == "syn_burst":
        events.extend(_syn(source, target, start))
    elif case == "http_payload":
        events.extend(_payload(source, target, start, TRAVERSAL))
    elif case == "scan_and_auth":
        events.extend(_scan(source, target, start, generator))
        events.extend(_auth(*_pair(origin, profile, 2), start))
    elif case == "correlated_scan_payload":
        events.extend(_scan(source, target, start, generator))
        events.extend(_payload(source, _pair(origin, profile, 2)[1], start, INJECTION))
    elif case == "scan_and_payload":
        events.extend(_scan(source, target, start, generator))
        events.extend(_payload(*_pair(origin, profile, 2), start, INJECTION))
    elif case == "triple_independent":
        events.extend(_auth(*_pair(origin, profile, 2), start))
        events.extend(_payload(*_pair(origin, profile, 3), start, TRAVERSAL))
        events.extend(_payload(*_pair(origin, profile, 4), start, INJECTION))
    else:
        events.extend(_auth(source, _pair(origin, profile, 2)[1], start))
        events.extend(_payload(source, _pair(origin, profile, 3)[1], start, TRAVERSAL))
        events.extend(_payload(source, _pair(origin, profile, 4)[1], start, INJECTION))
    return events


def _pair(origin: int, profile: int, offset: int) -> tuple[str, str]:
    return (
        f"192.0.2.{origin + profile + offset}",
        f"198.51.100.{origin + profile + offset}",
    )


def _event(source, target, moment, *, port=443, protocol="TCP", flags="A",
           status=None, uri=None) -> NetworkEvent:
    return NetworkEvent(
        timestamp=moment, src_ip=source, dst_ip=target, dst_port=port,
        protocol=protocol, tcp_flags=flags, http_status=status, http_uri=uri,
        http_method="GET" if uri is not None else None,
        http_host=target if uri is not None else None,
        bytes=len(uri or "") + 120, simulated=True,
    )


def _scan(source, target, start, generator) -> list[NetworkEvent]:
    first = generator.randrange(2000, 40000)
    return [
        _event(source, target, start + timedelta(seconds=index * 3), port=first + index)
        for index in range(10)
    ]


def _auth(source, target, start) -> list[NetworkEvent]:
    return [
        _event(source, target, start + timedelta(seconds=index * 20),
               protocol="HTTP", status=401)
        for index in range(5)
    ]


def _syn(source, target, start) -> list[NetworkEvent]:
    return [
        _event(source, target, start + timedelta(milliseconds=index * 400), flags="S")
        for index in range(20)
    ]


def _payload(source, target, start, uri) -> list[NetworkEvent]:
    return [_event(source, target, start, protocol="HTTP", status=200, uri=uri)]


def _http(source, target, start, status, uri, count) -> list[NetworkEvent]:
    return [
        _event(source, target, start + timedelta(seconds=index * 5),
               protocol="HTTP", status=status, uri=uri)
        for index in range(count)
    ]
