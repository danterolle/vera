"""Generate the perturbed evaluation set from a VERA training split.

The set rewrites existing examples so that only the property under test changes:
alert count, entity identity, scope, untrusted instructions, evidence availability,
language or conversation context. Nothing is taken from the validation or test split.

    uv run python -m finetuning.perturb.build \
        --dataset .vera/datasets/vera-domain-v1/train \
        --output .vera/finetuning/perturbed.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from .alerts import alert_counts
from .context import build_case, group_by_task, load_example
from .families import (
    entity_swap,
    italian_question,
    missing_evidence,
    out_of_scope,
    previous_turn,
    prompt_injection,
)

BUILDERS = (
    alert_counts,
    entity_swap,
    out_of_scope,
    prompt_injection,
    missing_evidence,
    italian_question,
    previous_turn,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="JSONL split, or a directory of sharded part-*.jsonl files",
    )
    parser.add_argument("--output", required=True, type=Path, help="destination JSONL")
    parser.add_argument("--seed", type=int, default=20261101)
    return parser.parse_args()


def load_split(path: Path) -> list[dict]:
    paths = sorted(path.glob("part-*.jsonl")) if path.is_dir() else [path]
    if not paths:
        raise ValueError(f"no JSONL shards found under {path}")
    return [
        json.loads(line)
        for jsonl in paths
        for line in jsonl.open()
        if line.strip()
    ]


def main() -> int:
    args = parse_args()
    by_task = group_by_task([load_example(example) for example in load_split(args.dataset)])

    rng = random.Random(args.seed)
    cases: list[dict] = []
    for builder in BUILDERS:
        for family, context, data, checks in builder(by_task, rng):
            cases.append(build_case(context, family, data, checks, len(cases) + 1))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as stream:
        for case in cases:
            stream.write(json.dumps(case) + "\n")

    counts = Counter(case["family"] for case in cases)
    print(f"wrote {len(cases)} cases to {args.output}")
    for family, count in sorted(counts.items()):
        print(f"  {family:12} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
