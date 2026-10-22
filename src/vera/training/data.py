import hashlib
import json
from collections import defaultdict
from pathlib import Path

from vera.providers.prompts import SYSTEM_PROMPT
from vera.training.records import TrainingRecord, fingerprint, validate_record
from vera.training.streams import FAMILIES


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_dataset(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported training dataset format")
    if manifest["system_prompt_sha256"] != fingerprint(SYSTEM_PROMPT):
        raise ValueError("The dataset was built for a different VERA system prompt")
    for relative, expected in manifest["files"].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f"Invalid dataset file: {relative}")
        if file_hash(path) != expected:
            raise ValueError(f"Dataset checksum mismatch: {relative}")
    assigned: set[str] = set()
    for split in ("train", "validation", "test"):
        groups = set(manifest["splits"][split]["source_groups"])
        if groups & assigned:
            raise ValueError("Source groups overlap across dataset splits")
        assigned |= groups
    return manifest


def read_records(directory: Path, split: str, limit: int = 0) -> list[TrainingRecord]:
    if split not in {"train", "validation", "test"} or limit < 0:
        raise ValueError("Invalid split or record limit")
    manifest = verify_dataset(directory)
    records = []
    allowed = set(manifest["splits"][split]["source_groups"]) | {f"stream-{FAMILIES[split]}"}
    for relative in sorted(manifest["files"]):
        if Path(relative).parts[0] == split:
            for line in (directory / relative).read_text().splitlines():
                record = TrainingRecord.model_validate_json(line)
                validate_record(record)
                if not record.groups or not set(record.groups).issubset(allowed):
                    raise ValueError("A training row references a group outside its split")
                records.append(record)
    if len(records) != manifest["splits"][split]["examples"]:
        raise ValueError(f"The {split} record count does not match the manifest")
    if not limit or len(records) <= limit:
        return records
    buckets: dict[str, list[TrainingRecord]] = defaultdict(list)
    for record in records:
        buckets[record.task].append(record)
    selected = []
    while len(selected) < limit:
        for name in sorted(buckets):
            if buckets[name] and len(selected) < limit:
                selected.append(buckets[name].pop())
    return selected


def encode_record(record: TrainingRecord, tokenizer, max_length: int) -> dict:
    messages = [message.model_dump() for message in record.messages]
    prefix = tokenizer.apply_chat_template(
        messages[:-1], tokenize=True, add_generation_prompt=True, enable_thinking=False,
        return_dict=False,
    )
    tokens = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False, enable_thinking=False,
        return_dict=False,
    )
    if tokens[:len(prefix)] != prefix:
        raise ValueError("The chat template cannot provide an exact assistant-only loss mask")
    if len(tokens) > max_length:
        raise ValueError(
            f"Record {record.id} needs {len(tokens)} tokens; limit is {max_length}. "
            "Increase the limit or rebuild shorter contexts; truncation is disabled."
        )
    labels = [-100] * len(prefix) + tokens[len(prefix):]
    if not any(value != -100 for value in labels):
        raise ValueError("The record contains no assistant target tokens")
    return {"input_ids": tokens, "attention_mask": [1] * len(tokens), "labels": labels}
