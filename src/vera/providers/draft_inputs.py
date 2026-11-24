from dataclasses import dataclass

from vera.domain.enums import ClaimStatus, Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.errors import ProviderError
from vera.providers.conversation import CONVERSATION_SYSTEM, conversation_prompt
from vera.providers.parsing import json_object
from vera.providers.prompts import SYSTEM_PROMPT, generation_prompt
from vera.providers.schema import answer_schema
from vera.reasoning.relevance import relevant_record_ids
from vera.retrieval.subjects import IDENTIFIERS


@dataclass(frozen=True)
class DraftInput:
    prompt: str
    system: str
    schema: dict
    conversational_scope: bool | None = None
    unavailable_only: bool = False

    def parse(self, content: str) -> GeneratedAnswer:
        payload = json_object(content)
        claims = payload.get("claims")
        scope = payload.get("out_of_scope")
        if self.conversational_scope is not None and (
            scope is not self.conversational_scope or claims != []
        ):
            raise ProviderError("Model response does not match the conversational intent")
        if scope is True and claims:
            raise ProviderError("An out-of-scope response cannot contain claims")
        draft = GeneratedAnswer.model_validate(payload)
        if self.unavailable_only and (
            scope is not False or len(draft.claims) != 1
            or draft.claims[0].status != ClaimStatus.UNAVAILABLE
            or draft.claims[0].evidence_ids or draft.claims[0].citations
        ):
            raise ProviderError("Model response did not abstain without matching evidence")
        return draft


def draft_inputs(
    request: AnalysisRequest,
    route: Route,
    plan: ResourcePlan | None,
    evidence: list[Evidence],
    alerts: list[DetectionAlert],
    statistics: StreamStatistics,
    feedback: list[str],
    response_language: str,
) -> DraftInput:
    if plan is not None and plan.intent != "cybersecurity":
        return DraftInput(
            conversation_prompt(request, plan, response_language),
            CONVERSATION_SYSTEM,
            answer_schema([], plan),
            conversational_scope=plan.intent == "out_of_scope",
        )
    subjects = IDENTIFIERS.findall(request.query)
    unavailable_only = False
    if subjects and not request.events and not alerts:
        records = relevant_record_ids(evidence, subjects)
        if not records:
            evidence = []
            unavailable_only = True
    return DraftInput(
        generation_prompt(
            request, route, evidence, alerts, statistics, feedback,
            response_language=response_language, plan=plan,
        ),
        SYSTEM_PROMPT,
        answer_schema(evidence, plan, unavailable_only=unavailable_only),
        unavailable_only=unavailable_only,
    )
