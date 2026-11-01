import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from vera_finetuning.data import digest, load_candidate


def load_excluded(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        return set()
    values = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("model") == "base":
            values.add(record["id"])
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select a leakage-audited, task-stratified validation pack"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-task", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--previous-answers", type=Path, action="append", default=[])
    parser.add_argument("--exclude-loss-sample", type=int, default=24)
    args = parser.parse_args()
    if args.per_task < 1 or args.exclude_loss_sample < 0:
        parser.error("Sample sizes must be non-negative and --per-task must be positive")
    if args.output.exists():
        parser.error("Choose a new output directory; existing evaluation packs are immutable")
    for path in args.previous_answers:
        if not path.is_file():
            parser.error(f"Previous-answer artifact does not exist: {path}")
    contract = json.loads(args.contract.read_text())
    splits, warnings = load_candidate(args.dataset, contract)
    previous_ids = set().union(*(load_excluded(path) for path in args.previous_answers))
    excluded_parent_ids = {
        row.get("alignment", {}).get("parent_id", row["id"])
        for row in splits["validation"][:args.exclude_loss_sample]
    }
    candidates = [
        row for row in splits["validation"]
        if row["id"] not in previous_ids
        and row.get("alignment", {}).get("parent_id", row["id"]) not in excluded_parent_ids
    ]
    grouped = {}
    for row in candidates:
        grouped.setdefault(row["task"], []).append(row)
    rng = random.Random(args.seed)
    selected = []
    for task in sorted(grouped):
        examples = list(grouped[task])
        rng.shuffle(examples)
        take = examples[:args.per_task]
        if len(take) < args.per_task:
            raise ValueError(f"{task} has only {len(take)} unseen evaluation examples")
        selected.extend(take)

    training_targets = {row["messages"][-1]["content"] for row in splits["train"]}
    training_groups = {group for row in splits["train"] for group in row["groups"]}
    training_sources = {source for row in splits["train"] for source in row["source_ids"]}
    training_entities = {
        entity for row in splits["train"] for entity in row["scenario"]["entities"]
    }
    if any(
        training_groups.intersection(row["groups"])
        or training_sources.intersection(row["source_ids"])
        or training_entities.intersection(row["scenario"]["entities"])
        for row in selected
    ):
        raise ValueError("Selected validation examples overlap training source groups")
    pack_target_counts = Counter(row["messages"][-1]["content"] for row in selected)
    records = [{
        "id": row["id"],
        "parent_id": row.get("alignment", {}).get("parent_id", row["id"]),
        "task": row["task"],
        "group_ids": row["groups"],
        "source_ids": row["source_ids"],
        "target_sha256": hashlib.sha256(
            row["messages"][-1]["content"].encode()
        ).hexdigest(),
        "target_seen_in_training": row["messages"][-1]["content"] in training_targets,
        "target_duplicate_in_pack": pack_target_counts[row["messages"][-1]["content"]] > 1,
    } for row in selected]

    args.output.mkdir(parents=True)
    selection = {
        "dataset_sha256": digest(args.dataset),
        "split": "validation", "seed": args.seed, "per_task": args.per_task,
        "excluded_prior_behavioral_ids": sum(
            row["id"] in previous_ids
            or row.get("alignment", {}).get("parent_id", row["id"]) in previous_ids
            for row in splits["validation"]
        ),
        "excluded_fixed_loss_sample_parent_ids": len(excluded_parent_ids),
        "selected_ids": [row["id"] for row in selected],
        "warnings": warnings,
    }
    (args.output / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    with (args.output / "cases.jsonl").open("w") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")
    report = {
        **{key: value for key, value in selection.items() if key != "selected_ids"},
        "examples": len(selected),
        "task_counts": dict(sorted(Counter(row["task"] for row in selected).items())),
        "target_seen_in_training": sum(row["target_seen_in_training"] for row in records),
        "target_unique_within_pack": len(pack_target_counts),
        "target_duplicate_rows_within_pack": sum(
            count - 1 for count in pack_target_counts.values() if count > 1
        ),
        "all_source_groups_disjoint_from_training": True,
        "test_split_used": False,
        "training_started": False,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
