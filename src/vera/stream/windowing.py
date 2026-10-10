from collections import Counter, defaultdict, deque
from collections.abc import Callable

from vera.domain.reports import DetectionAlert
from vera.domain.requests import NetworkEvent

IndexedEvent = tuple[int, NetworkEvent]


def group_events(
    events: list[NetworkEvent],
    predicate: Callable[[NetworkEvent], bool],
) -> dict[tuple[str, str], list[IndexedEvent]]:
    groups: dict[tuple[str, str], list[IndexedEvent]] = defaultdict(list)
    for index, event in enumerate(events):
        if predicate(event):
            groups[(event.src_ip, event.dst_ip)].append((index, event))
    for samples in groups.values():
        samples.sort(key=lambda sample: sample[1].timestamp)
    return groups


def first_window(
    samples: list[IndexedEvent],
    threshold: int,
    seconds: int,
) -> list[IndexedEvent]:
    window: deque[IndexedEvent] = deque()
    for sample in samples:
        trim_window(window, sample[1], seconds)
        window.append(sample)
        if len(window) >= threshold:
            return list(window)
    return []


def trim_window(
    window: deque[IndexedEvent],
    current: NetworkEvent,
    seconds: int,
    ports: Counter[int] | None = None,
) -> None:
    while window and (current.timestamp - window[0][1].timestamp).total_seconds() > seconds:
        _, removed = window.popleft()
        if ports is not None and removed.dst_port is not None:
            ports[removed.dst_port] -= 1
            if ports[removed.dst_port] == 0:
                del ports[removed.dst_port]


def window_alert(samples: list[IndexedEvent], **values) -> DetectionAlert:
    return DetectionAlert(
        **values,
        event_indexes=[index for index, _ in samples],
        first_seen=samples[0][1].timestamp,
        last_seen=samples[-1][1].timestamp,
    )
