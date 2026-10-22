import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vera.domain.evidence import Evidence
from vera.domain.reports import GeneratedAnswer
from vera.providers.prompts import SYSTEM_PROMPT
from vera.reasoning.validation import validate_and_repair


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class TrainingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task: str
    groups: list[str]
    source_ids: list[str]
    origin: Literal["synthetic_template"] = "synthetic_template"
    messages: list[Message]


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def context_from_prompt(prompt: str) -> dict:
    context, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])
    if not isinstance(context, dict):
        raise ValueError("The generation context must be an object")
    return context


def check_answer(payload: dict, context: dict) -> GeneratedAnswer:
    if set(payload) != {"summary", "claims", "out_of_scope"}:
        raise ValueError("The answer must contain exactly the VERA generation keys")
    if not isinstance(payload["out_of_scope"], bool):
        raise ValueError("out_of_scope must be a JSON boolean")
    if payload["out_of_scope"] and payload["claims"]:
        raise ValueError("Out-of-scope answers cannot contain claims")
    answer = GeneratedAnswer.model_validate(payload)
    if len(answer.claims) > 3:
        raise ValueError("The answer contains more than three claims")
    evidence = [Evidence.model_validate(item) for item in context["evidence"]]
    outcome = validate_and_repair(answer, evidence, repair=False)
    if outcome.errors:
        raise ValueError("; ".join(outcome.errors))
    registry = {item.id: item for item in evidence}
    for claim in answer.claims:
        for citation in claim.citations:
            if citation.supporting_quote not in registry[citation.evidence_id].content:
                raise ValueError("The quotation is not an exact substring of the source")
            if claim.status.value == "supported_fact" and claim.text != citation.supporting_quote:
                raise ValueError("Supported claim text must exactly equal its quotation")
    return answer


def validate_record(record: TrainingRecord) -> None:
    if [message.role for message in record.messages] != ["system", "user", "assistant"]:
        raise ValueError("Training records require one system/user/assistant exchange")
    if record.messages[0].content != SYSTEM_PROMPT:
        raise ValueError("The training system prompt differs from the runtime prompt")
    context = context_from_prompt(record.messages[1].content)
    check_answer(json.loads(record.messages[2].content), context)
    if record.id != fingerprint([message.model_dump() for message in record.messages]):
        raise ValueError("The training record fingerprint does not match its messages")


def semantic_fingerprint(record: TrainingRecord) -> str:
    context = context_from_prompt(record.messages[1].content)
    evidence = context["evidence"]
    return fingerprint({
        "task": record.task,
        "query": context["query"],
        "evidence": sorted(
            [{key: value for key, value in item.items() if key != "id"} for item in evidence],
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
        "alerts": context["alerts"],
        "statistics": context["statistics"],
        "validation_feedback": context["validation_feedback"],
    })
