import json

from pydantic import ValidationError

from vera.domain.reports import DetectionAlert, GeneratedAnswer
from vera.evaluation.contract import strict_answer, used_fallback
from vera.reasoning.relevance import analysis_subjects
from vera.reasoning.summary import summary_review_errors
from vera.reasoning.validation import validate_and_repair
from vera_finetuning.contracts import context_evidence, parse_context
from vera_finetuning.evaluation import extract_json


def score_answer(record: dict, example: dict, coverage: float) -> dict:
    target = json.loads(example["messages"][-1]["content"])
    context = parse_context(example)
    evidence = context_evidence(context)
    subjects = (
        analysis_subjects(
            context["query"], [DetectionAlert.model_validate(item) for item in context["alerts"]],
            resolved_query=context["resolved_question"],
            current_subject=context.get("current_subject"),
        )
        if context["conversational_intent"] == "cybersecurity" else []
    )
    by_id = {item.id: item for item in evidence}
    result = {key: record.get(key) for key in ("model", "id", "task", "seconds", "output_tokens")}
    expected = {claim["status"] for claim in target["claims"]}
    result.update(
        provider_fallback=used_fallback(record), raw_contract_valid=False,
        unavailable_expected="unavailable" in expected, simulated_expected="simulated" in expected,
        status_recall=0.0, status_precision=0.0, guarded_status_recall=0.0,
        summary_requires_review=True,
    )
    payload = extract_json(record["answer"])
    result["json_valid"] = payload is not None
    if payload is None:
        result.update(schema_valid=False, validation_failures=None, errors=["invalid JSON"])
        return result
    try:
        if json.loads(record["answer"]) != payload:
            raise ValueError("Answer is not a standalone JSON object")
        strict_answer(payload)
        result["raw_contract_valid"] = True
    except ValueError as error:
        result["raw_contract_errors"] = [str(error)]
    try:
        answer = GeneratedAnswer.model_validate(payload)
    except ValidationError as error:
        result.update(schema_valid=False, validation_failures=None, errors=[str(error)])
        return result
    result["normalization_changed"] = payload != answer.model_dump(mode="json")
    outcome = validate_and_repair(
        answer, evidence, repair=False, minimum_coverage=coverage, subjects=subjects,
    )
    guarded = validate_and_repair(
        answer, evidence, repair=True, minimum_coverage=coverage, subjects=subjects,
    )
    checked = validate_and_repair(
        guarded.draft, evidence, repair=False, minimum_coverage=coverage, subjects=subjects,
    )
    actual = {claim.status.value for claim in answer.claims}
    guarded_actual = {claim.status.value for claim in guarded.draft.claims}
    supported = [claim for claim in answer.claims if claim.status.value == "supported_fact"]
    summary_errors = (
        summary_review_errors(answer.summary, answer.claims)
        if context["conversational_intent"] == "cybersecurity" and not answer.out_of_scope else []
    )
    result.update(
        schema_valid=True,
        out_of_scope=answer.out_of_scope,
        out_of_scope_correct=answer.out_of_scope == target["out_of_scope"],
        guarded_out_of_scope=guarded.draft.out_of_scope,
        guarded_out_of_scope_correct=guarded.draft.out_of_scope == target["out_of_scope"],
        claims=len(answer.claims),
        expected_statuses=sorted(expected),
        actual_statuses=sorted(actual),
        guarded_statuses=sorted(guarded_actual),
        status_recall=len(expected & actual) / len(expected) if expected else float(not actual),
        status_precision=len(expected & actual) / len(actual) if actual else float(not expected),
        statuses_exact=expected == actual,
        guarded_status_recall=(
            len(expected & guarded_actual) / len(expected)
            if expected else float(not guarded_actual)
        ),
        relevance_failures=sum(
            "does not concern" in error or "no supplied record concerns" in error
            for error in outcome.errors
        ),
        scope_guard_failures=sum("marked out of scope" in error for error in outcome.errors),
        missing_statuses=sorted(expected - actual),
        unexpected_statuses=sorted(actual - expected),
        guarded_missing_statuses=sorted(expected - guarded_actual),
        guarded_unexpected_statuses=sorted(guarded_actual - expected),
        unavailable_present="unavailable" in actual,
        guarded_unavailable_present="unavailable" in guarded_actual,
        simulated_present="simulated" in actual,
        supported_fact_on_memory=sum(
            any(by_id[item].source == "memory" for item in claim.evidence_ids if item in by_id)
            for claim in supported
        ),
        supported_claims=len(supported),
        exact_quote_claims=sum(
            bool(claim.citations) and all(
                citation.supporting_quote == claim.text
                and citation.evidence_id in by_id
                and citation.supporting_quote in by_id[citation.evidence_id].content
                for citation in claim.citations
            ) for claim in supported
        ),
        validation_failures=len(outcome.errors),
        guarded_validation_failures=len(checked.errors),
        citation_failures=sum(
            any(term in error.casefold() for term in ("citation", "quote", "grounded", "supported"))
            for error in outcome.errors
        ),
        summary_requires_review=bool(summary_errors),
        raw_behavior_pass=(
            result["raw_contract_valid"] and not outcome.errors
            and answer.out_of_scope == target["out_of_scope"]
            and expected == actual and not result["provider_fallback"]
        ),
        errors=outcome.errors,
        summary_errors=summary_errors,
    )
    return result
