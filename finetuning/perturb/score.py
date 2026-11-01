"""Score the perturbed challenge with VERA output and citation validation."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from vera_finetuning.data import load_candidate

from vera.config import Settings

from .scoring import paired_exact, score_case, summarize, summarize_groups


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--set", required=True, type=Path, dest="perturbed_set")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    splits, _ = load_candidate(args.dataset, contract)
    answers = load_jsonl(args.answers)
    cases = {case["id"]: case for case in load_jsonl(args.perturbed_set)}
    coverage = Settings(_env_file=None).grounding_min_coverage
    rows_by_model = defaultdict(list)
    for record in answers:
        case = cases.get(record["id"])
        if case is None:
            raise ValueError(f"Unknown evaluation case: {record['id']}")
        row = score_case(record, case, coverage)
        rows_by_model[record["model"]].append(row)
    report = {
        "scorer": "vera-pydantic-and-production-citation-validation",
        "minimum_coverage": coverage,
        "raw_property_comparison": paired_exact(rows_by_model, "raw_rule_pass"),
        "runtime_normalized_comparison": paired_exact(rows_by_model, "rule_pass"),
        "grounded_behavior_comparison": paired_exact(rows_by_model, "grounded_behavior_pass"),
        "models": {
            model: {
                "overall": summarize(rows),
                "by_family": summarize_groups(rows, "family"),
                "by_task": summarize_groups(rows, "task"),
                "results": rows,
            }
            for model, rows in rows_by_model.items()
        },
    }
    output = args.output or args.answers.with_name("scores-production.json")
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "raw_property_comparison": report["raw_property_comparison"],
        "runtime_normalized_comparison": report["runtime_normalized_comparison"],
        "grounded_behavior_comparison": report["grounded_behavior_comparison"],
        "models": {name: item["overall"] for name,item in report["models"].items()},
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
