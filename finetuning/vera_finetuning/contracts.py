import json

from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.prompts import generation_prompt
from vera.reasoning.validation import validate_and_repair

INTENTS = {"cybersecurity", "social", "out_of_scope", "clarification"}


def parse_context(example: dict) -> dict:
    prompt = example["messages"][1]["content"]
    return json.JSONDecoder().raw_decode(prompt[prompt.index("{") :])[0]


def context_evidence(context: dict) -> list[Evidence]:
    evidence = []
    for item in context["evidence"]:
        record = dict(item)
        record["metadata"] = {
            key: record.pop(key) for key in ("provenance", "lookup_method") if key in record
        }
        evidence.append(Evidence.model_validate(record))
    return evidence


def validate_example(
    example: dict, minimum_coverage: float, response_language: str
) -> None:
    messages = example["messages"]
    context = parse_context(example)
    intent = context["conversational_intent"]
    if intent not in INTENTS:
        raise ValueError(f"Unknown conversational intent: {intent}")
    evidence = context_evidence(context)
    answer = GeneratedAnswer.model_validate_json(messages[2]["content"])
    _validate_intent(intent, answer)
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
        context["feedback"], response_language=response_language, plan=plan,
    )
    if rebuilt != messages[1]["content"]:
        raise ValueError(
            "The dataset does not use the current runtime's input format; rebuild it first"
        )


def _validate_intent(intent: str, answer: GeneratedAnswer) -> None:
    if intent in {"social", "clarification"} and (answer.claims or answer.out_of_scope):
        raise ValueError(f"{intent} answers must carry no claims and stay in scope")
    if intent == "out_of_scope" and (not answer.out_of_scope or answer.claims):
        raise ValueError("Out-of-scope answers must set out_of_scope and carry no claims")
    if intent == "cybersecurity" and answer.out_of_scope:
        raise ValueError("Cybersecurity answers cannot be marked out of scope")
