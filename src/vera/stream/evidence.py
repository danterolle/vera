import json
from collections import defaultdict

from vera.domain.enums import SEVERITY_ORDER
from vera.domain.reports import DetectionAlert, StreamStatistics


def summarize_stream(
    statistics: StreamStatistics,
    alerts: list[DetectionAlert],
) -> tuple[str, dict]:
    groups: dict[str, list[DetectionAlert]] = defaultdict(list)
    for alert in alerts:
        groups[alert.rule_id].append(alert)
    summaries = []
    for rule_id, values in sorted(groups.items()):
        indexes = sorted({index for alert in values for index in alert.event_indexes})
        first_seen = min(
            (alert.first_seen for alert in values if alert.first_seen is not None),
            default=None,
        )
        last_seen = max(
            (alert.last_seen for alert in values if alert.last_seen is not None),
            default=None,
        )
        highest = max(values, key=lambda alert: SEVERITY_ORDER[alert.severity])
        summaries.append(
            {
                "rule_id": rule_id,
                "title": highest.title,
                "severity": highest.severity.value,
                "technique_id": highest.technique_id,
                "cve_ids": sorted({cve for alert in values for cve in alert.cve_ids}),
                "occurrences": len(values),
                "observed_count": sum(alert.observed_count for alert in values),
                "threshold": highest.threshold,
                "window_seconds": highest.window_seconds,
                "confidence": max(alert.confidence for alert in values),
                "first_seen": first_seen.isoformat() if first_seen else None,
                "last_seen": last_seen.isoformat() if last_seen else None,
                "event_indexes_sample": indexes[:100],
                "omitted_event_indexes": max(0, len(indexes) - 100),
            }
        )
    payload = {
        "statistics": statistics.model_dump(mode="json"),
        "alert_summaries": summaries,
    }
    metadata = {
        "event_count": statistics.total_events,
        "alert_count": len(alerts),
        "rule_counts": {
            rule_id: len(values) for rule_id, values in sorted(groups.items())
        },
    }
    return json.dumps(payload, sort_keys=True), metadata
