import hashlib
import json
from collections.abc import Callable
from contextlib import ExitStack
from itertools import combinations
from pathlib import Path
from zipfile import ZipFile

MODEL_ID = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
SPLITS = ("train", "validation", "test")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_package(archive_path: Path) -> tuple[dict, dict, dict[str, bytes]]:
    with ExitStack() as resources:
        read: Callable[[str], bytes]
        if archive_path.is_dir():
            members = list(archive_path.rglob("*"))
            if any(item.is_symlink() for item in members):
                raise ValueError("Dataset contents must not contain symbolic links")
            paths = [item for item in members if item.is_file()]
            names = [item.relative_to(archive_path).as_posix() for item in paths]
            size = sum(item.stat().st_size for item in paths)

            def read_file(name: str) -> bytes:
                return (archive_path / name).read_bytes()

            read = read_file
        else:
            archive = resources.enter_context(ZipFile(archive_path))
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
            size = sum(item.file_size for item in archive.infolist())
            read = archive.read
        if len(names) != len(set(names)) or len(names) > 256:
            raise ValueError("The archive contains duplicate names or too many files")
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise ValueError("Dataset filenames must stay within the package")
        if size > 128 * 1024 * 1024:
            raise ValueError("The uncompressed dataset exceeds the 128 MiB limit")
        if "package.json" not in names:
            raise ValueError("The dataset package manifest is missing")
        package_bytes = read("package.json")
        package = json.loads(package_bytes)
        declared_files = set(package["files"]) | {"package.json"}
        if set(names) != declared_files:
            raise ValueError("The archive contains undeclared or missing package files")
        if package["purpose"] != "domain_sft_candidate":
            raise ValueError("Expected a VERA domain SFT candidate")
        files = {name: read(name) for name in package["files"]}
        files["package.json"] = package_bytes
        for name, expected in package["files"].items():
            if hashlib.sha256(files[name]).hexdigest() != expected:
                raise ValueError(f"Dataset checksum mismatch: {name}")
    return package, json.loads(files["manifest.json"]), files


def load_candidate(archive_path: Path, contract: dict) -> tuple[dict, list[str]]:
    if archive_path.is_file() and digest(archive_path) != contract["archive_sha256"]:
        raise ValueError("The dataset archive differs from the locally reviewed package")
    package, manifest, files = read_package(archive_path)
    if hashlib.sha256(files["package.json"]).hexdigest() != contract["package_sha256"]:
        raise ValueError("The dataset package differs from the reviewed contract")
    if hashlib.sha256(files["manifest.json"]).hexdigest() != contract["manifest_sha256"]:
        raise ValueError("The dataset manifest differs from the reviewed contract")
    warnings = []
    if manifest.get("human_reviewed") is not True:
        warnings.append("The targets are synthetic and have not been reviewed by an expert.")
    if package.get("training_authorized") is not True:
        warnings.append("This archive does not authorize training; explicit consent is required.")
    if manifest["system_prompt_sha256"] != contract["system_prompt_sha256"]:
        warnings.append(
            "The historical manifest's prompt hash is inconsistent; actual prompts "
            "must match the independently captured runtime contract."
        )
    splits = {
        split: [
            json.loads(line)
            for name in sorted(files)
            if name.startswith(f"{split}/") and name.endswith(".jsonl")
            for line in files[name].decode().splitlines() if line.strip()
        ]
        for split in SPLITS
    }
    group_sets = {}
    factual_sets = {}
    for split, examples in splits.items():
        if not examples or len(examples) != manifest["splits"][split]["examples"]:
            raise ValueError(f"Missing examples or incorrect split count: {split}")
        group_sets[split], factual_sets[split] = set(), set()
        for example in examples:
            messages = example["messages"]
            if [item["role"] for item in messages] != ["system", "user", "assistant"]:
                raise ValueError(f"Unexpected conversation roles: {example['id']}")
            if messages[0]["content"] != contract["system_prompt"]:
                raise ValueError(
                    "Dataset/runtime prompt drift: rebuild and review the dataset before training"
                )
            target = json.loads(messages[-1]["content"])
            if set(target) != {"summary", "claims", "out_of_scope"}:
                raise ValueError(f"Unexpected target schema: {example['id']}")
            if len(target["claims"]) > contract["max_claims"]:
                raise ValueError(f"Too many target claims: {example['id']}")
            group_sets[split].update(example["groups"])
            factual_sets[split].update(
                claim["text"] for claim in target["claims"]
                if claim["status"] == "supported_fact"
            )
    for left, right in combinations(SPLITS, 2):
        if group_sets[left] & group_sets[right] or factual_sets[left] & factual_sets[right]:
            raise ValueError(f"Cross-split leakage: {left}/{right}")
    return splits, warnings


def encode_example(tokenizer, example: dict, max_length: int) -> dict:
    messages = example["messages"]
    prefix = tokenizer.apply_chat_template(
        messages[:-1], tokenize=True, return_dict=False,
        add_generation_prompt=True, enable_thinking=False,
    )
    complete = tokenizer.apply_chat_template(
        messages, tokenize=True, return_dict=False,
        add_generation_prompt=False, enable_thinking=False,
    )
    if complete[:len(prefix)] != prefix or len(complete) <= len(prefix):
        raise ValueError(f"The assistant-only token boundary is invalid: {example['id']}")
    if len(complete) > max_length:
        raise ValueError(
            f"{example['id']} needs {len(complete)} tokens; no silent truncation is permitted"
        )
    return {"input_ids": complete, "prefix_length": len(prefix), "id": example["id"]}


def tokenize_splits(tokenizer, splits: dict, max_length: int = 2048) -> tuple[dict, dict]:
    encoded = {}
    report = {}
    for split, examples in splits.items():
        encoded[split] = [encode_example(tokenizer, row, max_length) for row in examples]
        report[split] = {
            "examples": len(examples),
            "maximum_tokens": max(len(item["input_ids"]) for item in encoded[split]),
            "maximum_target_tokens": max(
                len(item["input_ids"]) - item["prefix_length"] for item in encoded[split]
            ),
        }
    return encoded, report
