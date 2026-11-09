import json
from collections import Counter
from pathlib import Path

from vera.domain.enums import ClaimStatus
from vera.domain.requests import NetworkEvent
from vera.stream.detectors import detect_events
from vera.stream.evidence import summarize_stream
from vera.stream.statistics import calculate_statistics
from vera_domain.models import (
    SourceFragment,
    TrainingRecord,
    context_from_prompt,
    file_hash,
    fingerprint,
    semantic_fingerprint,
)
from vera_domain.partition import normalized_text, split_fragments

SPLITS = ("train", "validation", "test")


def load_rows(directory: Path, prefix: str, manifest: dict) -> list[dict]:
    return [
        json.loads(line) for relative in sorted(manifest["files"])
        if relative.startswith(prefix + "/") and relative.endswith(".jsonl")
        for line in (directory / relative).read_text().splitlines()
    ]


def audit_domain_dataset(directory: Path, *, enforce_diversity: bool = True) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    _verify_files(directory, manifest)
    sources, groups = _load_sources(directory, manifest)
    partitions, assignments = split_fragments(list(sources.values()), manifest["seed"])
    for identifier, group in groups.items():
        if assignments[identifier] != group:
            raise ValueError("A source-fragment split group is wrong")
    source_splits = {item.id: split for split, items in partitions.items() for item in items}
    report = {
        "passed": True, "human_reviewed": False, "purpose": manifest["purpose"],
        "dataset_version": manifest.get("dataset_version"), "training_authorized": False,
        "model_trainability_verified": False,
        "dataset_sha256": file_hash(directory / "manifest.json"),
        "unique_source_fragments": len(sources),
        "unique_source_entities": len({item.entity_id for item in sources.values()}),
        "label_method": "Extractive official evidence plus deterministic defensive scenario rules.",
        "split_method": "CVE/product, technique, identical and near-duplicate source grouping.",
        "limitations": manifest["limitations"], "splits": {},
    }
    seen: set[str] = set()
    source_truths: set[str] = set()
    entity_splits: dict[str, str] = {}
    for split in SPLITS:
        records = load_rows(directory, split, manifest)
        replays = {row["id"]: row for row in load_rows(directory, f"replays/{split}", manifest)}
        stats = _audit_split(
            split, records, sources, source_splits, replays, seen, entity_splits, source_truths,
        )
        if dict(sorted(stats["tasks"].items())) != manifest["splits"][split]["tasks"]:
            raise ValueError("The task coverage differs from its manifest")
        source_truths |= stats.pop("facts")
        report["splits"][split] = stats
    if enforce_diversity:
        _require_diversity(report["splits"])
    return report


def _audit_split(split, records, sources, source_splits, replays, seen, entity_splits,
                 source_truths) -> dict:
    tasks: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    claim_counts: Counter[int] = Counter()
    outcomes: Counter[str] = Counter()
    alerts: Counter[int] = Counter()
    intents: Counter[str] = Counter()
    turns: Counter[int] = Counter()
    families: Counter[str] = Counter()
    facts: set[str] = set()
    multi_evidence = 0
    for record in records:
        record = TrainingRecord.model_validate(record)
        signature = semantic_fingerprint(record)
        if signature in seen:
            raise ValueError("Duplicate domain scenarios")
        seen.add(signature)
        metadata = record.scenario
        if record.origin != "source_grounded_synthetic":
            raise ValueError("The scenario does not declare its synthetic provenance")
        for entity in metadata.entities:
            if entity in entity_splits and entity_splits[entity] != split:
                raise ValueError("An entity is reused across dataset splits")
            entity_splits[entity] = split
        if set(record.source_ids) != set(metadata.source_bindings.values()):
            raise ValueError("The source bindings do not match the provenance ledger")
        context = context_from_prompt(record.messages[1].content)
        evidence = {item["id"]: item for item in context["evidence"]}
        for identifier, source_id in metadata.source_bindings.items():
            if source_splits.get(source_id) != split or identifier not in evidence:
                raise ValueError("A source is missing or leaks across dataset splits")
            item, original = evidence[identifier], sources[source_id]
            if item["content"] != original.content or original.content not in original.original:
                raise ValueError("Context evidence was altered from its original source")
        answer = json.loads(record.messages[-1].content)
        if len(answer["claims"]) > 6:
            raise ValueError("An answer exceeds the six-claim contract")
        for claim in answer["claims"]:
            statuses[claim["status"]] += 1
            if claim["status"] == ClaimStatus.SUPPORTED_FACT.value:
                for citation in claim["citations"]:
                    source_id = metadata.source_bindings.get(citation["evidence_id"])
                    if source_id not in sources:
                        raise ValueError("An authoritative claim has no official source")
                    if claim["text"] not in sources[source_id].content:
                        raise ValueError("The authoritative target is not grounded in its source")
                    if any(
                        citation["supporting_quote"] != claim["text"]
                        for citation in claim["citations"]
                    ):
                        raise ValueError("A factual target differs from its quotation")
                    if sources[source_id].entity_id not in metadata.entities:
                        raise ValueError("The factual target cites an unrelated entity")
                    facts.add(normalized_text(claim["text"]))
        _audit_decision(record.task, context, answer)
        if metadata.event_replay_id is not None:
            outcomes[_audit_replay(context, answer, metadata.event_replay_id, replays)] += 1
        if context["conversational_intent"] != metadata.intent:
            raise ValueError("The context intent differs from its scenario metadata")
        if context["response_language"] != metadata.language:
            raise ValueError("The response language differs from its scenario metadata")
        if len(context["conversation"]) != metadata.conversation_turns:
            raise ValueError("The conversation length differs from its scenario metadata")
        alerts[metadata.alert_count] += 1
        intents[metadata.intent] += 1
        turns[metadata.conversation_turns] += 1
        if metadata.detector_family is not None:
            families[metadata.detector_family] += 1
        claim_counts[len(answer["claims"])] += 1
        multi_evidence += len({
            item["evidence_id"] for claim in answer["claims"] for item in claim["citations"]
        }) >= 2
        tasks[record.task] += 1
    if facts & source_truths:
        raise ValueError("Verbatim factual targets leak across splits")
    return {
        "examples": len(records), "tasks": dict(sorted(tasks.items())),
        "claim_statuses": dict(sorted(statuses.items())),
        "claims_per_answer": {str(k): v for k, v in sorted(claim_counts.items())},
        "unique_factual_texts": len(facts), "multi_evidence_answers": multi_evidence,
        "traffic_outcomes": dict(outcomes), "alert_counts": _stringify(alerts),
        "intents": _stringify(intents), "conversation_turns": _stringify(turns),
        "traffic_families": dict(sorted(families.items())), "facts": facts,
    }


def _audit_replay(context: dict, answer: dict, identifier: str, replays: dict) -> str:
    replay = replays[identifier]
    if fingerprint(replay["events"]) != identifier:
        raise ValueError("A replay fingerprint was changed")
    events = [NetworkEvent.model_validate(item) for item in replay["events"]]
    alerts = detect_events(events)
    statistics = calculate_statistics(events)
    content, _ = summarize_stream(statistics, alerts)
    if context["alerts"] != [item.model_dump(mode="json") for item in alerts]:
        raise ValueError("The traffic target does not match the actual detector output")
    if context["statistics"] != statistics.model_dump(mode="json"):
        raise ValueError("The traffic statistics do not match the actual events")
    if context["evidence"][0]["content"] != content:
        raise ValueError("The stream evidence does not match the replay")
    if sorted(item.rule_id for item in alerts) != sorted(replay["expected_rules"]):
        raise ValueError("The declared traffic outcome is wrong")
    expected = [alert.description for alert in alerts] or [
        f"No configured detection threshold was met across {len(events)} events."
    ]
    if [claim["text"] for claim in answer["claims"]] != expected:
        raise ValueError("The simulated target does not describe the computed observations")
    if {claim["status"] for claim in answer["claims"]} != {"simulated"}:
        raise ValueError("Controlled traffic findings must remain simulated")
    if context["route"] != ("FULL" if alerts else "STREAM"):
        raise ValueError("The selected stream route disagrees with the detector output")
    return f"alerts_{len(alerts)}"


def _audit_decision(task: str, context: dict, answer: dict) -> None:
    statuses = {claim["status"] for claim in answer["claims"]}
    if answer["out_of_scope"] != (task == "scope_boundary"):
        raise ValueError("A scenario has the wrong domain-scope decision")
    if task in {"missing_record", "memory_only"} and statuses != {"unavailable"}:
        raise ValueError("Missing authoritative evidence must remain unavailable")
    if task == "current_status" and statuses != {"supported_fact", "unavailable"}:
        raise ValueError("A snapshot must not silently replace current live verification")
    if task == "review_revision" and not context["feedback"]:
        raise ValueError("The synthetic revision lacks its analyst feedback")
    if (
        task in {"social_conversation", "clarification"}
        and (statuses or context["conversational_intent"] != task.split("_")[0])
    ):
        raise ValueError("Social and clarification turns cannot carry factual claims")


def _require_diversity(splits: dict) -> None:
    train = splits["train"]
    if (
        train["unique_factual_texts"] < 1500 or train["multi_evidence_answers"] < 300
        or len(splits["validation"]["tasks"]) < 12 or len(splits["test"]["tasks"]) < 12
    ):
        raise ValueError("The candidate does not meet minimum content-diversity requirements")
    for split, values in splits.items():
        if split == "train" and not {"0", "1", "2", "3"} <= set(values["alert_counts"]):
            raise ValueError("Train misses an alert-count profile")
        if split != "train" and len(values["alert_counts"]) < 3:
            raise ValueError(f"{split} misses an alert-count profile")
        if not {"social", "clarification", "out_of_scope"} <= set(values["intents"]):
            raise ValueError(f"{split} misses a conversational intent")
        if not any(int(key) > 0 for key in values["conversation_turns"]):
            raise ValueError(f"{split} misses multi-turn conversations")
        if not {"correlated_scan_payload", "triple_correlated"} & set(values["traffic_families"]):
            raise ValueError(f"{split} misses an alert-correlation replay")


def _load_sources(
    directory: Path, manifest: dict,
) -> tuple[dict[str, SourceFragment], dict[str, str]]:
    rows = load_rows(directory, "sources", manifest)
    sources = {
        row["id"]: SourceFragment.model_validate(
            {key: value for key, value in row.items() if key != "group"}
        ) for row in rows
    }
    if len(sources) != len(rows):
        raise ValueError("Duplicate source-fragment IDs")
    return sources, {row["id"]: row["group"] for row in rows}


def _verify_files(directory: Path, manifest: dict) -> None:
    for relative, expected in manifest["files"].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f"Invalid dataset file: {relative}")
        if file_hash(path) != expected:
            raise ValueError(f"Dataset checksum mismatch: {relative}")


def _stringify(values: Counter) -> dict[str, int]:
    return {str(key): value for key, value in sorted(values.items())}
