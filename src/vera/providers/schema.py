import re

from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import GeneratedAnswer

MAX_CLAIMS = 6


def answer_schema(evidence: list[Evidence], plan: ResourcePlan | None) -> dict:
    schema = GeneratedAnswer.model_json_schema()
    schema["required"] = [*schema.get("required", []), "out_of_scope"]
    schema["properties"]["claims"]["maxItems"] = MAX_CLAIMS
    if plan is not None and plan.intent != "cybersecurity":
        schema["properties"]["claims"]["maxItems"] = 0
        schema["properties"]["out_of_scope"]["const"] = plan.intent == "out_of_scope"
    claim_schema = schema["$defs"]["Claim"]
    claim_schema["required"] = ["text", "status", "evidence_ids", "citations"]
    evidence_ids = list(dict.fromkeys(item.id for item in evidence))
    if evidence_ids:
        claim_schema["properties"]["evidence_ids"]["items"]["enum"] = evidence_ids
        schema["$defs"]["Citation"]["properties"]["evidence_id"]["enum"] = evidence_ids
    quotes = []
    for item in evidence:
        passages = re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z])", item.content)
        quotes.extend(part.strip() for part in passages if 20 <= len(part.strip()) <= 300)
        if len(item.content) <= 300:
            quotes.append(item.content)
    if quotes:
        schema["$defs"]["Citation"]["properties"]["supporting_quote"]["enum"] = list(
            dict.fromkeys(quotes)
        )[:12]
    return schema
