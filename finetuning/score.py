import argparse
import json
from collections import defaultdict
from pathlib import Path

from vera_finetuning.data import load_candidate
from vera_finetuning.score_summary import summarize
from vera_finetuning.scoring import score_answer

from vera.config import Settings


def sorted_group(rows: list[dict], key: str) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return dict(sorted(grouped.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Score raw and repaired VERA answers separately")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-coverage", type=float)
    args = parser.parse_args()
    output = args.output or args.answers.with_name("scores.json")
    if output.exists():
        parser.error("Choose a new report path; existing reports are immutable")
    coverage = args.minimum_coverage
    if coverage is None:
        coverage = Settings(_env_file=None).grounding_min_coverage
    if not 0 <= coverage <= 1:
        parser.error("--minimum-coverage must be between zero and one")
    contract = json.loads(args.contract.read_text())
    splits, _ = load_candidate(args.dataset, contract)
    examples = {example["id"]: example for split in splits.values() for example in split}
    expected = None
    if args.selection:
        selection = json.loads(args.selection.read_text())
        if selection["dataset_sha256"] != contract["archive_sha256"]:
            parser.error("Selection and dataset hashes differ")
        selected_ids = selection["selected_ids"]
        expected = set(selected_ids)
        if not expected or len(expected) != len(selected_ids) or expected - examples.keys():
            parser.error("Selection must contain unique known example IDs")
    rows, seen = [], set()
    for line in args.answers.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["model"], record["id"])
        if key in seen:
            raise ValueError(f"Duplicate model/example answer: {key}")
        if record["id"] not in examples:
            raise ValueError(f"Unknown example: {record['id']}")
        if record["task"] != examples[record["id"]]["task"]:
            raise ValueError(f"Incorrect task for {record['id']}")
        seen.add(key)
        rows.append(score_answer(record, examples[record["id"]], coverage))
    models = sorted_group(rows, "model")
    if not models:
        raise ValueError("No answers to score")
    expected = expected or {row["id"] for row in rows}
    for model, model_rows in models.items():
        if {row["id"] for row in model_rows} != expected:
            raise ValueError(f"{model}: incomplete or unpaired answer set")
    report = {
        "minimum_coverage": coverage,
        "answers": str(args.answers),
        "selection_verified": args.selection is not None,
        "production_authorized": False,
        "models": {
            model: {
                "overall": summarize(model_rows),
                "by_task": {
                    task: summarize(task_rows)
                    for task, task_rows in sorted_group(model_rows, "task").items()
                },
            }
            for model, model_rows in models.items()
        },
        "results": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    for model, summary in report["models"].items():
        print(f"=== {model} ===")
        print(json.dumps(summary["overall"], indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
