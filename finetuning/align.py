import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from vera_finetuning.alignment import align_example, rows, split_summary, write_candidate
from vera_finetuning.data import (
    MODEL_ID,
    MODEL_REVISION,
    SPLITS,
    digest,
    read_package,
    tokenize_splits,
)

from vera.config import Settings
from vera.providers.prompts import SYSTEM_PROMPT


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Align a copy without changing targets or sources")
    parser.add_argument("--dataset", type=Path, default=root / "vera-domain-v1.zip")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.dataset.resolve():
        parser.error("Choose a new output path; the original must remain unchanged")
    from transformers import AutoTokenizer

    parent_hash = digest(args.dataset)
    _, manifest, files = read_package(args.dataset)
    source_rows = rows(files, "sources")
    sources = {item["id"]: item for item in source_rows}
    if len(sources) != len(source_rows):
        raise ValueError("Duplicate source ledger IDs")
    coverage = Settings(_env_file=None).grounding_min_coverage
    splits = {}
    for split in SPLITS:
        originals = rows(files, split)
        splits[split] = [align_example(item, sources, coverage) for item in originals]
        if len(splits[split]) != manifest["splits"][split]["examples"]:
            raise ValueError(f"Split size changed unexpectedly: {split}")
        print(f"Validated {split}: {len(splits[split])} examples", flush=True)
    summary = split_summary(splits)
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
    )
    _, tokens = tokenize_splits(tokenizer, splits, max_length=3072)
    observed = max(item["maximum_tokens"] for item in tokens.values())
    max_length = max(2048, ((observed + 255) // 256) * 256)
    manifest.update({
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "human_reviewed": False, "training_authorized": False,
        "alignment": {
            "method": "canonical_runtime_prompt",
            "parent_archive_sha256": parent_hash,
            "assistant_targets_changed": 0, "source_records_changed": 0,
            "split_assignments_changed": 0,
            "runtime_revision": subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
            ).strip(),
        },
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_candidate(
        args.output, files, manifest, splits, summary, tokens, max_length,
    )
    if digest(args.dataset) != parent_hash:
        raise RuntimeError("The original dataset changed during alignment")
    print(json.dumps({
        "output": str(args.output), "parent_archive_sha256": parent_hash,
        "archive_sha256": digest(args.output), "max_length": max_length,
        "tokens": tokens, "assistant_targets_changed": 0,
        "human_reviewed": False, "training_authorized": False,
        "training_started": False,
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
