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
        description="Select a leakage-audited, task-stratified evaluation pack"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    parser.add_argument("--per-task", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--previous-answers", type=Path, action="append", default=[])
    parser.add_argument("--previous-dataset", type=Path)
    parser.add_argument("--previous-contract", type=Path)
    parser.add_argument(
        "--exclude-loss-sample",
        type=int,
        default=None,
        help="Validation-only rows held out for loss monitoring (default 24).",
    )
    args = parser.parse_args()
    exclude_loss_sample = args.exclude_loss_sample
    if exclude_loss_sample is None:
        exclude_loss_sample = 24 if args.split == "validation" else 0
    if args.split == "test" and (
        exclude_loss_sample or args.previous_answers or args.previous_dataset
    ):
        parser.error(
            "--split test does not accept validation-only prior-answer or loss-sample exclusions"
        )
    if args.per_task < 1 or exclude_loss_sample < 0 or args.max_new_tokens < 1:
        parser.error(
            "--per-task and --max-new-tokens must be positive; exclusions cannot be negative"
        )
    if args.output.exists():
        parser.error("Choose a new output directory; existing evaluation packs are immutable")
    for path in args.previous_answers:
        if not path.is_file():
            parser.error(f"Previous-answer artifact does not exist: {path}")
    if bool(args.previous_dataset) != bool(args.previous_contract):
        parser.error("--previous-dataset and --previous-contract must be supplied together")
    contract = json.loads(args.contract.read_text())
    splits, warnings = load_candidate(args.dataset, contract)
    previous_ids = set().union(*(load_excluded(path) for path in args.previous_answers))
    previous_parent_ids = set()
    if args.previous_dataset:
        previous_contract = json.loads(args.previous_contract.read_text())
        previous_splits, _ = load_candidate(args.previous_dataset, previous_contract)
        previous_parent_by_id = {
            row["id"]: row.get("alignment", {}).get("parent_id", row["id"])
            for row in previous_splits["validation"]
        }
        unmatched_ids = previous_ids - previous_parent_by_id.keys()
        if unmatched_ids:
            raise ValueError(
                f"Previous answers contain IDs absent from the previous validation "
                f"dataset: {len(unmatched_ids)}"
            )
        previous_parent_ids = {previous_parent_by_id[item] for item in previous_ids}
    elif previous_ids and not previous_ids.intersection(
        row["id"] for row in splits["validation"]
    ):
        raise ValueError(
            "Previous answers use IDs from another aligned dataset; pass its "
            "--previous-dataset and --previous-contract to map parent IDs"
        )
    excluded_parent_ids = {
        row.get("alignment", {}).get("parent_id", row["id"])
        for row in splits[args.split][:exclude_loss_sample]
    }
    candidates = [
        row for row in splits[args.split]
        if row["id"] not in previous_ids
        and row.get("alignment", {}).get("parent_id", row["id"]) not in previous_parent_ids
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
        "split": args.split, "seed": args.seed, "per_task": args.per_task,
        "max_new_tokens": args.max_new_tokens,
        "response_language": contract.get("response_language"),
        "excluded_prior_behavioral_ids": sum(
            row["id"] in previous_ids
            or row.get("alignment", {}).get("parent_id", row["id"]) in previous_parent_ids
            for row in splits[args.split]
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
        "test_split_used": args.split == "test",
        "training_started": False,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
