from collections import Counter

from vera.domain.reports import StreamStatistics
from vera.domain.requests import NetworkEvent


def calculate_statistics(events: list[NetworkEvent]) -> StreamStatistics:
    return StreamStatistics(
        total_events=len(events),
        total_bytes=sum(event.bytes for event in events),
        protocols=dict(Counter(event.protocol for event in events).most_common()),
        source_ips=dict(Counter(event.src_ip for event in events).most_common(10)),
        destination_ports=dict(
            Counter(
                str(event.dst_port) for event in events if event.dst_port is not None
            ).most_common(20)
        ),
    )
