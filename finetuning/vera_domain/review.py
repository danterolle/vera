import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from vera_domain.review_checks import inspect
from vera_domain.review_markdown import render

SPLITS = ("train", "validation", "test")
QUOTAS = {
    "social_conversation": 6, "clarification": 4, "stream_triage": 8,
    "defensive_guidance": 6, "multiturn_followup": 6, "language_variant": 6,
    "scope_boundary": 5, "concept_definition": 5, "vulnerability_triage": 5,
    "graph_evidence": 5,
}


def load_dataset(dataset: Path) -> tuple[dict, str, dict[str, list[dict]]]:
    if dataset.is_dir():
        raw = (dataset / "manifest.json").read_bytes()
        rows = {
            split: [
                json.loads(line)
                for path in sorted((dataset / split).glob("*.jsonl"))
                for line in path.read_text().splitlines() if line.strip()
            ] for split in SPLITS
        }
    else:
        with ZipFile(dataset) as archive:
            raw = archive.read("manifest.json")
            rows = {
                split: [
                    json.loads(line) for name in sorted(archive.namelist())
                    if name.startswith(split + "/") and name.endswith(".jsonl")
                    for line in archive.read(name).decode().splitlines() if line.strip()
                ] for split in SPLITS
            }
    return json.loads(raw), hashlib.sha256(raw).hexdigest(), rows


def select(rows: dict[str, list[dict]], seed: int) -> list[tuple[str, dict]]:
    generator = random.Random(seed)
    tasks = sorted({row["task"] for split in SPLITS for row in rows[split]})
    selected: list[tuple[str, dict]] = []
    for task in tasks:
        if task != "stream_triage":
            buckets = {
                split: [row for row in rows[split] if row["task"] == task]
                for split in SPLITS
            }
            selected.extend(_round_robin(buckets, QUOTAS.get(task, 3), generator))
            continue
        for alerts in range(4):
            buckets = {
                split: [
                    row for row in rows[split]
                    if row["task"] == task and row["scenario"]["alert_count"] == alerts
                ] for split in SPLITS
            }
            selected.extend(_round_robin(buckets, 2, generator))
    return selected


def _round_robin(buckets, quota, generator):
    for values in buckets.values():
        generator.shuffle(values)
    picked, index = [], 0
    while len(picked) < quota and any(buckets.values()):
        split = SPLITS[index % len(SPLITS)]
        if buckets[split]:
            picked.append((split, buckets[split].pop()))
        index += 1
    return picked


def build_pack(dataset: Path, output: Path, seed: int = 20261111) -> dict:
    manifest, digest, rows = load_dataset(dataset)
    cases = []
    for number, (split, row) in enumerate(select(rows, seed), 1):
        context, target, evidence, checks = inspect(row)
        cases.append({
            "review_id": f"rv-{number:04d}", "dataset_id": row["id"], "split": split,
            "task": row["task"], "intent": row["scenario"]["intent"],
            "language": row["scenario"]["language"], "question": context.get("query"),
            "context": context, "target": target, "evidence": evidence,
            "automated_checks": checks,
            "review": {"verdict": None, "reviewer": None, "notes": None, "reviewed_at": None},
        })
    failures = {
        case["review_id"]: [
            name for name, value in case["automated_checks"].items() if value is not True
        ] for case in cases
        if any(value is not True for value in case["automated_checks"].values())
    }
    report = {
        "dataset_sha256": digest, "dataset_version": manifest.get("dataset_version"),
        "seed": seed, "examples": len(cases),
        "task_counts": dict(sorted(Counter(case["task"] for case in cases).items())),
        "split_counts": dict(sorted(Counter(case["split"] for case in cases).items())),
        "automated_failures": failures,
        "human_reviewed": False, "training_authorized": False,
    }
    output.mkdir(parents=True)
    with (output / "cases.jsonl").open("w") as stream:
        for case in cases:
            stream.write(json.dumps(case, ensure_ascii=True) + "\n")
    (output / "REVIEW.md").write_text(render(cases, report))
    with (output / "review.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["review_id", "split", "task", "intent", "verdict", "reviewer", "notes"]
        )
        for case in cases:
            writer.writerow(
                [case["review_id"], case["split"], case["task"], case["intent"], "", "", ""]
            )
    (output / "signoff.json").write_text(json.dumps({
        "dataset_sha256": digest, "reviewer": None, "reviewed_at": None,
        "authorized": False, "notes": "",
    }, indent=2) + "\n")
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def summarize(directory: Path) -> dict:
    lines = (directory / "cases.jsonl").read_text().splitlines()
    cases = [json.loads(line) for line in lines if line]
    signoff = json.loads((directory / "signoff.json").read_text())
    valid = {"accept", "fix", "reject"}
    verdicts = Counter(
        case["review"]["verdict"] for case in cases
        if case["review"]["verdict"] in valid
    )
    unresolved = [
        case["review_id"] for case in cases if case["review"]["verdict"] not in valid
    ]
    missing_notes = [
        case["review_id"] for case in cases
        if case["review"]["verdict"] in {"fix", "reject"} and not case["review"]["notes"]
    ]
    ready = (
        bool(signoff.get("reviewer")) and not unresolved and not missing_notes
        and verdicts["accept"] == len(cases)
    )
    summary = {
        "examples": len(cases), "verdicts": dict(sorted(verdicts.items())),
        "unresolved": unresolved, "missing_notes": missing_notes,
        "reviewer": signoff.get("reviewer"), "ready_for_authorization": ready,
        "human_reviewed": ready, "signoff_authorized": signoff.get("authorized") is True,
        "training_authorized": False,
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
