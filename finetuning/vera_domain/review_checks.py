import json

from vera_finetuning.contracts import validate_example

from vera_domain.models import context_from_prompt

NO_ALERT = "No configured detection threshold was met across {events} events."


def inspect(row: dict) -> tuple[dict, dict, dict, dict]:
    context = context_from_prompt(row["messages"][1]["content"])
    target = json.loads(row["messages"][-1]["content"])
    evidence = {item["id"]: item for item in context.get("evidence", [])}
    checks = {
        "target_schema": set(target) == {"summary", "claims", "out_of_scope"},
        "citations_resolve": all(
            citation["evidence_id"] in evidence
            for claim in target.get("claims", [])
            for citation in claim.get("citations", [])
        ),
        "scope_matches_intent": _scope_matches(context, target),
    }
    factual = [
        claim for claim in target.get("claims", [])
        if claim["status"] == "supported_fact"
    ]
    checks["factual_quotes_verbatim"] = all(
        claim["text"] == citation["supporting_quote"]
        and citation["supporting_quote"] in evidence[citation["evidence_id"]]["content"]
        for claim in factual for citation in claim.get("citations", [])
    )
    if row["task"] == "stream_triage":
        checks["alert_claims_match"] = _alerts_match(context, target)
    try:
        validate_example(row, 0.55, context.get("response_language", "English"))
        checks["contract"] = True
    except Exception as error:
        checks["contract"] = f"{type(error).__name__}: {error}"
    return context, target, evidence, checks


def _scope_matches(context: dict, target: dict) -> bool:
    intent = context.get("conversational_intent")
    claims = target.get("claims", [])
    if intent in {"social", "clarification"}:
        return not target.get("out_of_scope") and not claims
    if intent == "out_of_scope":
        return target.get("out_of_scope") is True and not claims
    return target.get("out_of_scope") is False


def _alerts_match(context: dict, target: dict) -> bool:
    alerts = context.get("alerts") or []
    expected = [alert["description"] for alert in alerts] or [
        NO_ALERT.format(events=context["statistics"]["total_events"])
    ]
    claims = target.get("claims", [])
    return (
        [claim["text"] for claim in claims] == expected
        and {claim["status"] for claim in claims} == {"simulated"}
    )
