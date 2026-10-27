import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from vera_finetuning.data import MODEL_ID, MODEL_REVISION, digest, load_candidate

from vera.config import Settings
from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.prompts import SYSTEM_PROMPT, generation_prompt
from vera.providers.schema import MAX_CLAIMS
from vera.reasoning.validation import validate_and_repair


def validate_example(example: dict, minimum_coverage: float) -> None:
    messages = example["messages"]
    context, _ = json.JSONDecoder().raw_decode(messages[1]["content"].split("\n", 1)[1])
    if context["conversational_intent"] != "cybersecurity":
        raise ValueError(
            "This pilot supports cybersecurity generation, not conversational profiles"
        )
    evidence = []
    for item in context["evidence"]:
        record = dict(item)
        record["metadata"] = {
            key: record.pop(key) for key in ("provenance", "lookup_method")
        }
        evidence.append(Evidence.model_validate(record))
    answer = GeneratedAnswer.model_validate_json(messages[2]["content"])
    outcome = validate_and_repair(
        answer, evidence, repair=False, minimum_coverage=minimum_coverage,
    )
    if outcome.errors:
        raise ValueError(f"{example['id']}: {outcome.errors}")
    request = AnalysisRequest.model_validate({
        "query": context["query"], "conversation": context["conversation"],
    })
    plan = ResourcePlan.model_validate({
        "intent": context["conversational_intent"],
        "resolved_query": context["resolved_question"],
    })
    rebuilt = generation_prompt(
        request, Route(context["route"]), evidence,
        [DetectionAlert.model_validate(item) for item in context["alerts"]],
        StreamStatistics.model_validate(context["statistics"]),
        context["feedback"], plan=plan,
    )
    if rebuilt != messages[1]["content"]:
        raise ValueError(
            "The dataset does not use the current runtime's input format; rebuild it first"
        )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build a reviewed, data-free Kaggle code bundle")
    parser.add_argument("--dataset", type=Path, default=root / "vera-domain-v1.zip")
    parser.add_argument(
        "--output", type=Path, default=root / ".vera/finetuning/vera-kaggle-training.zip",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("The output already exists; choose a new --output path")
    with ZipFile(args.dataset) as archive:
        manifest_hash = hashlib.sha256(archive.read("manifest.json")).hexdigest()
    contract = {
        "model": MODEL_ID, "model_revision": MODEL_REVISION,
        "archive_sha256": digest(args.dataset), "manifest_sha256": manifest_hash,
        "system_prompt": SYSTEM_PROMPT,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "max_claims": MAX_CLAIMS,
        "source_revision": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
        ).strip(),
        "training_authorized": False,
    }
    splits, warnings = load_candidate(args.dataset, contract)
    minimum_coverage = Settings(_env_file=None).grounding_min_coverage
    count = 0
    for examples in splits.values():
        for example in examples:
            validate_example(example, minimum_coverage)
            count += 1
    contract["validated_examples"] = count
    contract["warnings"] = warnings
    args.output.parent.mkdir(parents=True, exist_ok=True)
    files = ("__init__.py", "data.py", "preflight.py", "model.py", "checkpoints.py", "train.py")
    with ZipFile(args.output, "x", compression=ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(root / "finetuning/vera_finetuning" / name, f"vera_finetuning/{name}")
        archive.write(root / "finetuning/requirements-kaggle.txt", "requirements-kaggle.txt")
        archive.write(root / "LICENSE", "LICENSE")
        archive.writestr("runtime-contract.json", json.dumps(contract, indent=2) + "\n")
    print(json.dumps({
        "bundle": str(args.output), "validated_examples": count, "warnings": warnings,
        "training_started": False, "dataset_modified": False,
    }, indent=2))


if __name__ == "__main__":
    main()
