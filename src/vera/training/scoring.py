import json

from vera.training.records import TrainingRecord, check_answer, context_from_prompt


def score_answer(text: str, record: TrainingRecord, *, truncated: bool = False) -> dict:
    expected = json.loads(record.messages[2].content)
    result = {
        "json_valid": False, "contract_valid": False, "scope_match": False,
        "status_match": False, "factual_source_match": False,
        "truncated": truncated, "passed": False, "error": None,
    }
    try:
        payload = json.loads(text)
        result["json_valid"] = isinstance(payload, dict)
        if not isinstance(payload, dict):
            raise ValueError("The answer must be a JSON object")
        answer = check_answer(payload, context_from_prompt(record.messages[1].content))
        result["contract_valid"] = True
        result["scope_match"] = answer.out_of_scope == expected["out_of_scope"]
        result["status_match"] = {claim.status.value for claim in answer.claims} == {
            claim["status"] for claim in expected["claims"]
        }
        expected_ids = {
            item for claim in expected["claims"] if claim["status"] == "supported_fact"
            for item in claim["evidence_ids"]
        }
        facts = [claim for claim in answer.claims if claim.status.value == "supported_fact"]
        result["factual_source_match"] = all(
            set(claim.evidence_ids).issubset(expected_ids) for claim in facts
        ) and (bool(facts) if expected_ids else not facts)
        result["passed"] = (
            not truncated and result["scope_match"] and result["status_match"]
            and result["factual_source_match"]
        )
    except ValueError as exc:
        result["error"] = str(exc)
    return result
