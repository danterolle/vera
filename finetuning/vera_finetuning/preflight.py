import argparse
import json
from pathlib import Path

from vera_finetuning.data import MODEL_ID, MODEL_REVISION, load_candidate, tokenize_splits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check data and tokenization without loading weights"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer

    contract = json.loads(args.contract.read_text())
    splits, warnings = load_candidate(args.dataset, contract)
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
    )
    _, tokens = tokenize_splits(tokenizer, splits, contract["max_length"])
    report = {
        "model": MODEL_ID, "revision": MODEL_REVISION, "tokens": tokens,
        "max_length": contract["max_length"],
        "input_storage": "directory" if args.dataset.is_dir() else "archive",
        "warnings": warnings, "weights_loaded": False, "training_started": False,
        "assistant_only_loss_boundary_verified": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
