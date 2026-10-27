import re

from vera.domain.interaction import InteractionPlan
from vera.domain.requests import AnalysisRequest
from vera.errors import ProviderError
from vera.retrieval.subjects import (
    IDENTIFIERS,
    concept_subject,
    explicit_security_topic,
    research_query,
)
from vera.workflow.runtime import Runtime

SOCIAL = re.compile(
    r"^(?:ciao|salve|buongiorno|buonasera|buonanotte|hey|hello|hi|grazie(?: mille)?|"
    r"thanks|thank you|ok(?:ay)?|va bene|a presto)[\s!.,?]*$", re.I,
)


def interpret(runtime: Runtime, request: AnalysisRequest) -> tuple[InteractionPlan, int, list[str]]:
    query = research_query(request.query, request.conversation) or request.query
    prev_topic = ""
    for msg in reversed(request.conversation):
        if msg.role == "user" and not SOCIAL.fullmatch(msg.content.strip()):
            subj = concept_subject(msg.content)
            if subj:
                prev_topic = subj
                break
            if explicit_security_topic(msg.content):
                prev_topic = msg.content.strip()[:100]
                break
    subject = concept_subject(query) or (prev_topic if not concept_subject(request.query) else "")
    search = (
        f"{prev_topic} {query}".strip()[:300]
        if prev_topic and not concept_subject(query)
        else (subject or query)[:300]
    )
    fallback = InteractionPlan(
        intent=(
            "social" if SOCIAL.fullmatch(request.query) and not request.events else "cybersecurity"
        ),
        resolved_query=query[:1000], subject=subject,
        search_query=search, needs_current=False,
    )
    if fallback.intent == "social" or request.events:
        return fallback, 0, []
    planner = getattr(runtime.provider, "interpret", None)
    if runtime.provider.external and planner:
        try:
            result = planner(request)
            if IDENTIFIERS.search(request.query) and result.intent != "cybersecurity":
                result = result.model_copy(update={"intent": "cybersecurity"})
            # A named topic, follow-up on previous context, or an explicit security identifier
            # needs evidence, not a generic clarification.
            if result.intent == "clarification" and (
                (result.subject and result.search_query)
                or explicit_security_topic(query)
                or bool(prev_topic)
                or bool(fallback.subject)
            ):
                resolved_subject = result.subject or fallback.subject or prev_topic
                result = result.model_copy(update={
                    "intent": "cybersecurity",
                    "subject": resolved_subject,
                    "search_query": (
                        result.search_query or fallback.search_query
                        or f"{resolved_subject} {query}"[:300]
                    ),
                })
            return result, 1, []
        except ProviderError as exc:
            return fallback, 1, [f"Conversation interpretation failed: {exc}"]
    return fallback, 0, []
