import argparse
import json

from vera.training.arguments import MODEL, REVISION
from vera.training.data import encode_record, read_records


def main() -> None:
    from pathlib import Path

    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser(description="Check VERA data lengths without loading weights.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    report = {}
    for split in ("train", "validation", "test"):
        records = read_records(args.data, split)
        encoded = [encode_record(record, tokenizer, args.max_length) for record in records]
        lengths = sorted(len(item["input_ids"]) for item in encoded)
        report[split] = {
            "examples": len(records), "maximum_tokens": lengths[-1],
            "median_tokens": lengths[len(lengths) // 2],
            "maximum_target_tokens": max(
                sum(token != -100 for token in item["labels"]) for item in encoded
            ),
        }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
