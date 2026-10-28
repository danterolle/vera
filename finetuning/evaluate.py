import argparse
from pathlib import Path

from vera_finetuning.evaluation import run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate base and adapter answers without scoring"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    parser.add_argument("--per-task", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    if args.per_task < 1:
        parser.error("--per-task must be positive")
    if args.max_new_tokens < 1:
        parser.error("--max-new-tokens must be positive")
    if args.adapter and not args.adapter.is_dir():
        parser.error("--adapter must point to a saved adapter directory")
    run(args)


if __name__ == "__main__":
    main()
