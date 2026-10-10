import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from vera.domain.requests import NetworkEvent
from vera.errors import StreamError


def load_events(path: Path, max_events: int = 10_000) -> list[NetworkEvent]:
    if not path.is_file():
        raise StreamError(f"Event file does not exist: {path}")
    if path.suffix.lower() not in {".json", ".jsonl"}:
        raise StreamError("Event input must use .json or .jsonl")
    try:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise StreamError("JSON event input must contain a list")
            records = payload
        else:
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        if len(records) > max_events:
            raise StreamError(f"Event input exceeds the {max_events} event limit")
        return [NetworkEvent.model_validate(record) for record in records]
    except json.JSONDecodeError as exc:
        raise StreamError(f"Invalid event JSON at line {exc.lineno}: {exc.msg}") from exc
    except ValidationError as exc:
        raise StreamError(f"Invalid normalized event: {exc}") from exc


def parse_tshark_output(output: str, max_events: int) -> list[NetworkEvent]:
    events: list[NetworkEvent] = []
    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 14:
            raise StreamError(f"Unexpected tshark output at line {line_number}")
        ip_src, ipv6_src, ip_dst, ipv6_dst = fields[1:5]
        try:
            events.append(
                NetworkEvent(
                    timestamp=datetime.fromtimestamp(float(fields[0]), tz=UTC),
                    src_ip=ip_src or ipv6_src,
                    dst_ip=ip_dst or ipv6_dst,
                    src_port=_optional_int(fields[5]),
                    dst_port=_optional_int(fields[6]),
                    protocol=fields[7] or "UNKNOWN",
                    tcp_flags=fields[8] or None,
                    http_method=fields[9] or None,
                    http_host=fields[10] or None,
                    http_uri=fields[11] or None,
                    http_status=_optional_int(fields[12]),
                    bytes=int(fields[13] or 0),
                )
            )
        except (ValueError, ValidationError) as exc:
            raise StreamError(f"Invalid tshark event at line {line_number}: {exc}") from exc
        if len(events) >= max_events:
            break
    return events


def _optional_int(value: str) -> int | None:
    return int(value) if value else None
