from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.state import GraphState
from vera.errors import ProviderError
from vera.workflow.runtime import Runtime


def assess_online_sources(
    runtime: Runtime, state: GraphState, plan: ResourcePlan, online: list[Evidence],
    *, subject: str | None,
) -> tuple[list[Evidence], int, list[str], int | None]:
    candidates = [
        item for item in online
        if item.source == SourceType.WEB and item.status == EvidenceStatus.AVAILABLE
    ]
    calls = state["model_calls"]
    if not candidates:
        return online, calls, [], None
    accepted = []
    warnings = []
    assessor = getattr(runtime.provider, "assess_sources", None)
    if assessor and (
        calls < runtime.settings.model_call_limit - 1 or state.get("revision_count", 0)
    ):
        calls += 1
        try:
            accepted = assessor(plan.resolved_query or state["request"].query, candidates)
        except ProviderError as exc:
            warnings.append(f"Online source assessment failed: {exc}")
    assessed = []
    for item in online:
        if item in candidates:
            if item.id in accepted:
                item = item.model_copy(update={"metadata": {
                    **item.metadata, "scope_validated": True,
                    "validated_topic": subject or item.metadata.get("research_subject"),
                }})
            else:
                item = item.model_copy(update={
                    "status": EvidenceStatus.UNAVAILABLE,
                    "content": "Online result was not validated as relevant cybersecurity context.",
                    "metadata": {**item.metadata, "scope_validated": False},
                })
        assessed.append(item)
    return assessed, calls, warnings, len(accepted)
