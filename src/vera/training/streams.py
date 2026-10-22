import random
from datetime import UTC, datetime, timedelta

from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.domain.reports import DetectionAlert, StreamStatistics
from vera.domain.requests import NetworkEvent
from vera.stream.detectors import detect_events
from vera.stream.evidence import summarize_stream
from vera.stream.statistics import calculate_statistics

FAMILIES = {"train": "port-scan", "validation": "authentication", "test": "syn-burst"}


def stream_context(
    split: str, generator: random.Random, *, benign: bool = False,
) -> tuple[Evidence, list[DetectionAlert], StreamStatistics]:
    family = FAMILIES[split]
    base = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=generator.randrange(86400))
    source = f"192.0.2.{generator.randrange(1, 255)}"
    destination = f"198.51.100.{generator.randrange(1, 255)}"
    count = {"port-scan": 10, "authentication": 5, "syn-burst": 20}[family]
    if benign:
        count = generator.randrange(1, count)
    first_port = generator.randrange(1024, 60000)
    events = [
        NetworkEvent(
            timestamp=base + timedelta(milliseconds=index * 100),
            src_ip=source,
            dst_ip=destination,
            dst_port=first_port + index if family == "port-scan" else 443,
            protocol="HTTP" if family == "authentication" else "TCP",
            http_status=401 if family == "authentication" else None,
            tcp_flags="S" if family == "syn-burst" else "A",
            bytes=generator.randrange(40, 300),
            simulated=True,
        )
        for index in range(count)
    ]
    alerts = detect_events(events)
    statistics = calculate_statistics(events)
    content, metadata = summarize_stream(statistics, alerts)
    evidence = make_evidence(
        SourceType.STREAM,
        "Synthetic stream observations",
        content,
        status=EvidenceStatus.SIMULATED,
        metadata=metadata,
    )
    return evidence, alerts, statistics
