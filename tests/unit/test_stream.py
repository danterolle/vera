from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from vera.data import resource
from vera.domain.requests import NetworkEvent
from vera.errors import StreamError
from vera.stream.detectors import detect_events
from vera.stream.parsers import load_events, parse_tshark_output
from vera.stream.pcap import PcapExtractor
from vera.stream.statistics import calculate_statistics


@pytest.mark.parametrize(
    ("filename", "expected_rules"),
    [
        ("benign-web.jsonl", set()),
        ("port-scan.jsonl", {"NET-PORT-SCAN"}),
        ("http-brute-force.jsonl", {"HTTP-AUTH-FAILURES"}),
        ("syn-flood.jsonl", {"TCP-SYN-BURST"}),
        (
            "web-exploitation.jsonl",
            {
                "HTTP-LOG4SHELL-PATTERN",
                "HTTP-PATH-TRAVERSAL",
                "HTTP-COMMAND-INJECTION",
            },
        ),
        (
            "network-events.jsonl",
            {
                "NET-PORT-SCAN",
                "HTTP-LOG4SHELL-PATTERN",
                "HTTP-PATH-TRAVERSAL",
            },
        ),
    ],
)
def test_sample_streams_trigger_expected_rules(
    filename: str,
    expected_rules: set[str],
) -> None:
    path = Path(str(resource(f"samples/{filename}")))
    events = load_events(path)
    alerts = detect_events(events)
    rule_ids = {alert.rule_id for alert in alerts}
    assert rule_ids == expected_rules
    assert all(event.simulated for event in events)
    assert calculate_statistics(events).total_events == len(events)
    if filename == "syn-flood.jsonl":
        assert alerts[0].technique_id == "T1498"
    for alert in alerts:
        assert alert.first_seen is not None
        assert alert.last_seen is not None
        assert alert.observed_count >= alert.threshold
        assert alert.confidence >= 0.5


def test_detection_thresholds_require_temporal_proximity() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    scan = [
        NetworkEvent(
            timestamp=start + timedelta(days=index),
            src_ip="203.0.113.1",
            dst_ip="10.0.0.1",
            src_port=40000 + index,
            dst_port=20 + index,
            protocol="TCP",
            tcp_flags="S",
        )
        for index in range(10)
    ]
    auth = [
        NetworkEvent(
            timestamp=start + timedelta(days=index),
            src_ip="198.51.100.1",
            dst_ip="10.0.0.2",
            dst_port=443,
            protocol="HTTP",
            http_status=401,
        )
        for index in range(5)
    ]
    assert detect_events(scan) == []
    assert detect_events(auth) == []


def test_tshark_output_is_normalized() -> None:
    line = (
        "1756540800\t192.0.2.1\t\t198.51.100.2\t\t50000\t443\tHTTP\t"
        "S\tGET\texample.test\t/index\t200\t128"
    )
    event = parse_tshark_output(line, 10)[0]
    assert event.src_ip == "192.0.2.1"
    assert event.dst_port == 443
    assert event.http_status == 200


def test_pcap_extractor_uses_restricted_argument_list(tmp_path, monkeypatch) -> None:
    capture = tmp_path / "capture.pcap"
    capture.write_bytes(b"controlled")
    line = (
        "1756540800\t192.0.2.1\t\t198.51.100.2\t\t50000\t443\tTCP\t"
        "S\t\t\t\t\t64"
    )
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout=line, stderr="")

    monkeypatch.setattr("vera.stream.pcap.shutil.which", lambda _: "/usr/bin/tshark")
    monkeypatch.setattr("vera.stream.pcap.subprocess.run", fake_run)
    events = PcapExtractor(max_events=25).extract(capture)
    assert len(events) == 1
    assert observed["command"][:3] == ["/usr/bin/tshark", "-r", str(capture.resolve())]
    assert observed["kwargs"]["check"] is False
    assert "shell" not in observed["kwargs"]


def test_pcap_extractor_reports_missing_tshark(tmp_path, monkeypatch) -> None:
    capture = tmp_path / "capture.pcap"
    capture.write_bytes(b"controlled")
    monkeypatch.setattr("vera.stream.pcap.shutil.which", lambda _: None)
    with pytest.raises(StreamError, match="tshark is required"):
        PcapExtractor().extract(capture)
