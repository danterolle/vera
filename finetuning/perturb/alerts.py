"""Alert-count perturbations for simulated stream replays.

Training data contains only zero or one configured signal, so asking for two or
three tests whether the adapter learned the counting rule or the sentence that
surrounds a single alert.
"""

from __future__ import annotations

import copy
import json
import random

from .context import PromptContext

Case = tuple[str, PromptContext, dict, dict]

ALERT_PLAN = ((0, 2), (2, 3), (3, 3))


def _synthetic_alert(index: int, rng: random.Random) -> dict:
    return {
        "rule_id": f"SYNTH-{index}-{rng.randint(100, 999)}",
        "title": f"Synthetic detection rule {index}",
        "description": (
            f"10.0.0.{rng.randint(10, 99)} generated {rng.randint(6, 40)} events "
            "within 300 seconds."
        ),
        "severity": rng.choice(["low", "medium", "high"]),
        "technique_id": rng.choice(["T1046", "T1059", "T1021"]),
        "cve_ids": [],
        "event_indexes": list(range(index, index + 4)),
        "observed_count": rng.randint(6, 40),
        "threshold": 5,
        "window_seconds": 300,
        "first_seen": "2026-06-01T07:10:00Z",
        "last_seen": "2026-06-01T07:14:00Z",
        "confidence": 0.7,
    }


def _resize(alerts: list[dict], expected: int, rng: random.Random) -> list[dict]:
    kept = list(alerts)[:expected]
    while len(kept) < expected:
        kept.append(_synthetic_alert(len(kept), rng))
    return kept


def _align_simulated(data: dict, alerts: list[dict]) -> None:
    for evidence in data.get("evidence", []):
        if evidence.get("status") != "simulated":
            continue
        try:
            payload = json.loads(evidence["content"])
        except (KeyError, TypeError, ValueError):
            continue
        payload["alert_summaries"] = [
            {
                "confidence": alert["confidence"],
                "cve_ids": alert["cve_ids"],
                "event_indexes_sample": alert["event_indexes"],
                "first_seen": alert["first_seen"],
                "last_seen": alert["last_seen"],
                "observed_count": alert["observed_count"],
                "occurrences": 1,
                "omitted_event_indexes": 0,
                "rule_id": alert["rule_id"],
                "severity": alert["severity"],
                "technique_id": alert["technique_id"],
                "threshold": alert["threshold"],
                "title": alert["title"],
                "window_seconds": alert["window_seconds"],
            }
            for alert in alerts
        ]
        evidence["content"] = json.dumps(payload, sort_keys=True)


def alert_counts(
    by_task: dict[str, list[PromptContext]], rng: random.Random
) -> list[Case]:
    sources = [ctx for ctx in by_task["stream_triage"] if ctx.data.get("alerts")]
    rng.shuffle(sources)
    expected_total = sum(copies for _, copies in ALERT_PLAN)
    cases: list[Case] = []
    for expected, copies in ALERT_PLAN:
        for context in sources[:copies]:
            data = copy.deepcopy(context.data)
            alerts = _resize(data.get("alerts") or [], expected, rng)
            data["alerts"] = alerts
            _align_simulated(data, alerts)
            cases.append(
                ("alerts", context, data, {"kind": "alerts", "expected": expected})
            )
    if len(cases) != expected_total:
        raise ValueError(
            f"family 'alerts' needs {expected_total} cases, built {len(cases)}"
        )
    return cases
