import shutil
import subprocess
from pathlib import Path

from vera.domain.requests import NetworkEvent
from vera.errors import StreamError
from vera.stream.parsers import parse_tshark_output

TSHARK_FIELDS = [
    "frame.time_epoch",
    "ip.src",
    "ipv6.src",
    "ip.dst",
    "ipv6.dst",
    "tcp.srcport",
    "tcp.dstport",
    "_ws.col.Protocol",
    "tcp.flags.str",
    "http.request.method",
    "http.host",
    "http.request.uri",
    "http.response.code",
    "frame.len",
]


class PcapExtractor:
    def __init__(self, max_events: int = 10_000, timeout_seconds: int = 60) -> None:
        self.max_events = max_events
        self.timeout_seconds = timeout_seconds

    def extract(self, path: Path) -> list[NetworkEvent]:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise StreamError(f"PCAP file does not exist: {resolved}")
        if resolved.suffix.lower() not in {".pcap", ".pcapng", ".cap"}:
            raise StreamError("PCAP input must use .pcap, .pcapng, or .cap")
        if resolved.stat().st_size > 100 * 1024 * 1024:
            raise StreamError("PCAP input exceeds the 100 MiB safety limit")
        executable = shutil.which("tshark")
        if executable is None:
            raise StreamError("tshark is required to process PCAP input")
        command = [
            executable,
            "-r",
            str(resolved),
            "-c",
            str(self.max_events),
            "-Y",
            "ip or ipv6",
            "-T",
            "fields",
            "-E",
            "separator=\t",
        ]
        for field in TSHARK_FIELDS:
            command.extend(["-e", field])
        try:
            process = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise StreamError("tshark exceeded the extraction time limit") from exc
        if process.returncode != 0:
            detail = process.stderr.strip()[:500] or "unknown tshark error"
            raise StreamError(f"tshark failed: {detail}")
        return parse_tshark_output(process.stdout, self.max_events)
