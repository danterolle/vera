import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vera_domain.review import build_pack, summarize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or summarize a human review pack for a VERA dataset; no training.",
    )
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument(
        "--summarize", type=Path,
        help="Read a filled pack directory and write summary.json.",
    )
    args = parser.parse_args()
    if args.summarize is not None:
        print(json.dumps(summarize(args.summarize), indent=2))
        return
    if args.dataset is None or args.output is None:
        parser.error("--dataset and --output are required unless --summarize is used")
    if not args.dataset.exists():
        parser.error(f"Dataset does not exist: {args.dataset}")
    if args.output.exists():
        parser.error("Choose a new output directory; review packs are immutable")
    report = build_pack(args.dataset, args.output, args.seed)
    print(json.dumps(report, indent=2))
    print(f"Review pack: {args.output.resolve()}")
    print("This pack contains dataset content. Review it locally; it does not authorize training.")


if __name__ == "__main__":
    main()
