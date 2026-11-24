from itertools import chain

from vera.domain.interaction import InteractionPlan
from vera.domain.requests import AnalysisRequest
from vera.errors import ProviderError
from vera.retrieval.subjects import IDENTIFIERS, concept_subject, names_subject, research_query
from vera.workflow.runtime import Runtime


def _has_named_subject(runtime: Runtime, query: str) -> bool:
    if IDENTIFIERS.search(query):
        return True
    subject = concept_subject(query)
    return subject is not None and any(
        names_subject(item, subject)
        for item in chain(runtime.knowledge.documents, runtime.corpus.documents)
    )


def interpret(runtime: Runtime, request: AnalysisRequest) -> tuple[InteractionPlan, int, list[str]]:
    query = research_query(request.query, request.conversation) or request.query
    prev_topic = ""
    for msg in reversed(request.conversation):
        if msg.role == "user":
            subj = concept_subject(msg.content)
            if subj:
                prev_topic = subj
                break
    subject = concept_subject(query) or (prev_topic if not concept_subject(request.query) else "")
    search = (
        f"{prev_topic} {query}".strip()[:300]
        if prev_topic and not concept_subject(query)
        else (subject or query)[:300]
    )
    fallback = InteractionPlan(
        intent="cybersecurity",
        resolved_query=query[:1000], subject=subject,
        search_query=search, needs_current=False,
    )
    if request.events:
        return fallback, 0, []
    planner = getattr(runtime.provider, "interpret", None)
    if runtime.provider.external and planner:
        try:
            result = planner(request)
            if _has_named_subject(runtime, request.query):
                result = fallback.model_copy(update={"needs_current": result.needs_current})
            return result, 1, []
        except ProviderError as exc:
            return fallback, 1, [f"Conversation interpretation failed: {exc}"]
    return fallback, 0, []
