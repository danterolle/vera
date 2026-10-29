import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from pydantic import ValidationError
from vera_finetuning.contracts import context_evidence, parse_context
from vera_finetuning.data import load_candidate
from vera_finetuning.evaluation import extract_json

from vera.config import Settings
from vera.domain.reports import GeneratedAnswer
from vera.reasoning.validation import validate_and_repair


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def score_answer(record: dict, example: dict, coverage: float) -> dict:
    target = json.loads(example["messages"][-1]["content"])
    evidence = context_evidence(parse_context(example))
    by_id = {item.id: item for item in evidence}
    result = {
        "model": record["model"],
        "id": record["id"],
        "task": record["task"],
        "seconds": record.get("seconds"),
        "output_tokens": record.get("output_tokens"),
    }
    payload = extract_json(record["answer"])
    result["json_valid"] = payload is not None
    if payload is None:
        result.update(schema_valid=False, validation_failures=None, errors=["invalid JSON"])
        return result
    try:
        answer = GeneratedAnswer.model_validate(payload)
    except ValidationError as error:
        result.update(
            schema_valid=False,
            validation_failures=None,
            errors=[str(item["msg"]) for item in error.errors()[:5]],
        )
        return result

    outcome = validate_and_repair(
        answer, evidence, repair=False, minimum_coverage=coverage,
    )
    expected = {claim["status"] for claim in target["claims"]}
    actual = {claim.status.value for claim in answer.claims}
    supported = [
        claim for claim in answer.claims if claim.status.value == "supported_fact"
    ]
    citation_terms = ("citation", "quote", "grounded", "supported fact")
    result.update(
        schema_valid=True,
        out_of_scope=answer.out_of_scope,
        out_of_scope_correct=answer.out_of_scope == target["out_of_scope"],
        claims=len(answer.claims),
        expected_statuses=sorted(expected),
        actual_statuses=sorted(actual),
        status_recall=(
            len(expected & actual) / len(expected)
            if expected else float(not actual)
        ),
        missing_statuses=sorted(expected - actual),
        unexpected_statuses=sorted(actual - expected),
        unavailable_expected="unavailable" in expected,
        unavailable_present="unavailable" in actual,
        simulated_expected="simulated" in expected,
        simulated_present="simulated" in actual,
        supported_fact_on_memory=sum(
            1
            for claim in supported
            if any(
                item_id in by_id and by_id[item_id].source == "memory"
                for item_id in claim.evidence_ids
            )
        ),
        supported_claims=len(supported),
        exact_quote_claims=sum(
            1
            for claim in supported
            if claim.citations
            and all(
                normalize(citation.supporting_quote) == normalize(claim.text)
                for citation in claim.citations
            )
        ),
        validation_failures=len(outcome.errors),
        citation_failures=sum(
            1
            for error in outcome.errors
            if any(term in error.casefold() for term in citation_terms)
        ),
        errors=outcome.errors[:5],
    )
    return result


def summarize(rows: list[dict]) -> dict:
    def rate(key: str) -> float:
        return mean(bool(row.get(key)) for row in rows)

    def mean_of(key: str) -> float | None:
        values = [row[key] for row in rows if row.get(key) is not None]
        return mean(values) if values else None

    expected_unavailable = [row for row in rows if row.get("unavailable_expected")]
    expected_simulated = [row for row in rows if row.get("simulated_expected")]
    valid = [row for row in rows if row.get("schema_valid")]
    supported = sum(row.get("supported_claims", 0) for row in rows)
    exact = sum(row.get("exact_quote_claims", 0) for row in rows)
    return {
        "examples": len(rows),
        "json_valid_rate": rate("json_valid"),
        "schema_valid_rate": rate("schema_valid"),
        "schema_valid_examples": len(valid),
        "scope_accuracy": rate("out_of_scope_correct"),
        "mean_status_recall": mean_of("status_recall"),
        "unavailable_presence_rate": (
            mean(bool(row.get("unavailable_present")) for row in expected_unavailable)
            if expected_unavailable else None
        ),
        "simulated_presence_rate": (
            mean(bool(row.get("simulated_present")) for row in expected_simulated)
            if expected_simulated else None
        ),
        "citation_failure_rate": (
            mean(bool(row["citation_failures"]) for row in valid) if valid else None
        ),
        "mean_validation_failures": mean_of("validation_failures"),
        "exact_quote_rate": exact / supported if supported else None,
        "memory_citation_violations": sum(
            row.get("supported_fact_on_memory", 0) for row in rows
        ),
        "mean_output_tokens": mean_of("output_tokens"),
        "mean_seconds": mean_of("seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score generated answers with VERA validation")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-coverage", type=float)
    args = parser.parse_args()
    coverage = args.minimum_coverage
    if coverage is None:
        coverage = Settings(_env_file=None).grounding_min_coverage
    contract = json.loads(args.contract.read_text())
    splits, _ = load_candidate(args.dataset, contract)
    examples = {example["id"]: example for split in splits.values() for example in split}
    rows = []
    for line in args.answers.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["id"] not in examples:
            raise ValueError(f"Unknown example in answers: {record['id']}")
        rows.append(score_answer(record, examples[record["id"]], coverage))

    models = defaultdict(list)
    for row in rows:
        models[row["model"]].append(row)
    report = {
        "minimum_coverage": coverage,
        "answers": str(args.answers),
        "models": {
            model: {
                "overall": summarize(model_rows),
                "by_task": {
                    task: summarize(task_rows)
                    for task, task_rows in sorted_group(model_rows, "task").items()
                },
            }
            for model, model_rows in models.items()
        },
        "results": rows,
    }
    output = args.output or args.answers.with_name("scores.json")
    output.write_text(json.dumps(report, indent=2) + "\n")
    for model, summary in report["models"].items():
        print(f"=== {model} ===")
        print(json.dumps(summary["overall"], indent=2))
    print(f"Wrote {output}")


def sorted_group(rows: list[dict], key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return dict(sorted(grouped.items()))


if __name__ == "__main__":
    main()
