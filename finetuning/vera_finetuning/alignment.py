import hashlib
import json
from collections import Counter
from itertools import combinations
from zipfile import ZIP_DEFLATED, ZipFile

from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.prompts import SYSTEM_PROMPT, generation_prompt
from vera.retrieval.subjects import research_query
from vera_finetuning.contracts import validate_example
from vera_finetuning.data import MODEL_ID, MODEL_REVISION, SPLITS

CONTENT_PREFIXES = ("licenses/", "replays/", "sources/", "train/", "validation/", "test/")

DATASET_DESCRIPTION = """# Mechanically aligned VERA candidate

This copy rebuilds system and user prompts for the current cybersecurity generation
contract. Original assistant targets, source text, split assignments, licenses and
controlled replay records are unchanged. Parent conversation IDs are retained.

This is not expert-reviewed data or production telemetry. Original short answers
have not been expanded into new reasoning. Scope negatives exercise cybersecurity
generation; this is not a conversational-intent or source-assessment dataset.

Use the included manifests, quality checks and real-tokenizer receipt. Mechanical
compatibility does not establish improved quality, T4 fit or deployment readiness.
Human review and training authorization remain false. A separately acknowledged
compatibility pilot is not authorization for a full training run.
"""


def rows(files: dict[str, bytes], prefix: str) -> list[dict]:
    return [
        json.loads(line)
        for name in sorted(files)
        if name.startswith(prefix + "/") and name.endswith(".jsonl")
        for line in files[name].decode().splitlines() if line.strip()
    ]


def align_example(original: dict, sources: dict, minimum_coverage: float) -> dict:
    messages = original["messages"]
    if [item["role"] for item in messages] != ["system", "user", "assistant"]:
        raise ValueError(f"Unexpected conversation roles: {original['id']}")
    context, _ = json.JSONDecoder().raw_decode(messages[1]["content"].split("\n", 1)[1])
    evidence = []
    for item in context["evidence"]:
        record = dict(item)
        source_id = original["scenario"]["source_bindings"].get(item["id"])
        if source_id is not None:
            if sources[source_id]["content"] != item["content"]:
                raise ValueError(f"Altered source fragment: {original['id']}")
            record["metadata"] = {"provenance": "bundled_snapshot"}
        evidence.append(Evidence.model_validate(record))
    request = AnalysisRequest.model_validate({"query": context["query"]})
    route = Route(context["route"])
    plan = ResourcePlan.model_validate({
        "intent": "cybersecurity", "resolved_query": research_query(request.query),
        "use_rag": route in {Route.CAG_RAG, Route.CAG_RAG_TOOL, Route.FULL},
        "use_tools": route == Route.CAG_RAG_TOOL,
        "use_stream": route in {Route.STREAM, Route.FULL},
    })
    rebuilt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": generation_prompt(
            request, route, evidence,
            [DetectionAlert.model_validate(item) for item in context["alerts"]],
            StreamStatistics.model_validate(context["statistics"]),
            context["validation_feedback"], plan=plan,
        )},
        dict(messages[-1]),
    ]
    identity = json.dumps(
        {"parent_id": original["id"], "messages": rebuilt}, sort_keys=True,
    ).encode()
    result = {
        **original, "id": hashlib.sha256(identity).hexdigest(), "messages": rebuilt,
        "alignment": {"parent_id": original["id"], "assistant_target_changed": False},
    }
    validate_example(result, minimum_coverage)
    if result["messages"][-1] != original["messages"][-1]:
        raise ValueError("Alignment must never rewrite an assistant target")
    return result


def split_summary(splits: dict) -> dict:
    identities = {}
    summary = {}
    for split, examples in splits.items():
        facts, groups, entities, sources = set(), set(), set(), set()
        statuses, tasks = Counter(), Counter()
        for example in examples:
            groups.update(example["groups"])
            entities.update(example["scenario"]["entities"])
            sources.update(example["source_ids"])
            tasks[example["task"]] += 1
            for claim in json.loads(example["messages"][-1]["content"])["claims"]:
                statuses[claim["status"]] += 1
                if claim["status"] == "supported_fact":
                    facts.add(claim["text"])
        identities[split] = (facts, groups, entities, sources)
        summary[split] = {
            "examples": len(examples), "tasks": dict(tasks),
            "claim_statuses": dict(statuses), "unique_factual_texts": len(facts),
        }
    for left, right in combinations(SPLITS, 2):
        if any(a & b for a, b in zip(identities[left], identities[right], strict=True)):
            raise ValueError(f"Cross-split leakage: {left}/{right}")
    return summary


def write_candidate(path, original_files, manifest, splits, summary, tokens, max_length):
    files = {
        name: content for name, content in original_files.items()
        if name.startswith(("licenses/", "sources/", "replays/"))
    }
    for split, examples in splits.items():
        files[f"{split}/part-000.jsonl"] = (
            "\n".join(json.dumps(item, ensure_ascii=False) for item in examples) + "\n"
        ).encode()
    files["DATASET.md"] = DATASET_DESCRIPTION.encode()
    manifest["files"] = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in files.items()
        if name.startswith(CONTENT_PREFIXES)
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    files["manifest.json"] = manifest_bytes
    files["quality-report.json"] = (json.dumps({
        "passed": True, "purpose": "domain_sft_candidate",
        "human_reviewed": False, "training_authorized": False,
        "model_trainability_verified": False, "dataset_sha256": manifest_hash,
        "assistant_targets_changed": 0, "source_records_changed": 0,
        "cross_split_overlap": 0, "splits": summary,
        "limitations": [
            "Mechanical alignment is not expert label review.",
            "Short existing answers have not been expanded or improved.",
            "T4 execution and quality improvement remain unverified.",
        ],
    }, indent=2) + "\n").encode()
    files["token-budget.json"] = (json.dumps({
        "dataset_sha256": manifest_hash, "model": MODEL_ID, "revision": MODEL_REVISION,
        "max_length": max_length, "assistant_loss_mask_verified": True,
        "truncation": False, "splits": tokens,
    }, indent=2) + "\n").encode()
    package = {
        "format_version": 1, "purpose": "domain_sft_candidate", "training_authorized": False,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
        archive.writestr("package.json", json.dumps(package) + "\n")
