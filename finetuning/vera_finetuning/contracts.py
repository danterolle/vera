import json

from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.prompts import generation_prompt
from vera.reasoning.validation import validate_and_repair


def parse_context(example: dict) -> dict:
    return json.JSONDecoder().raw_decode(
        example["messages"][1]["content"].split("\n", 1)[1]
    )[0]


def context_evidence(context: dict) -> list[Evidence]:
    evidence = []
    for item in context["evidence"]:
        record = dict(item)
        record["metadata"] = {
            key: record.pop(key) for key in ("provenance", "lookup_method")
        }
        evidence.append(Evidence.model_validate(record))
    return evidence


def validate_example(example: dict, minimum_coverage: float) -> None:
    messages = example["messages"]
    context = parse_context(example)
    if context["conversational_intent"] != "cybersecurity":
        raise ValueError(
            "This pilot supports cybersecurity generation, not conversational profiles"
        )
    evidence = context_evidence(context)
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
