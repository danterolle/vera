from vera.domain.enums import ClaimStatus
from vera.domain.reports import RunMetrics
from vera.domain.review import ReviewRecord, ReviewStatus
from vera.domain.state import GraphState
from vera.workflow.knowledge_graph import graph_metadata
from vera.workflow.provenance import STALE_DRAFT, draft_metadata, has_current_validation


def pending_review(
    state: GraphState, *, version: int, history: list[str], created_at: str | None,
    revision_supported: bool,
) -> ReviewRecord:
    current = has_current_validation(state)
    reasons = list(state["review_reasons"])
    if not current:
        reasons.append(STALE_DRAFT)
    claims = state["draft"].claims
    return ReviewRecord(
        run_id=state["run_id"],
        session_id=state["request"].session_id,
        created_at=state.get("request_received_at", created_at),
        status=ReviewStatus.PENDING,
        version=version,
        reasons=reasons,
        query=state["request"].query,
        route=state["route"],
        draft=state["draft"],
        evidence=state["evidence"],
        incident=state["incident"],
        reflection=state["reflection"],
        warnings=state["warnings"],
        revision_count=state.get("revision_count", 0),
        can_approve=current,
        can_revise=revision_supported and state.get("revision_count", 0) < 2,
        feedback_history=history,
        error=state.get("revision_error"),
        metadata={
            **draft_metadata(state),
            "origin": state["request"].origin,
            "intent": state["resource_plan"].intent,
            "resource_plan": state["resource_plan"].model_dump(mode="json"),
            "knowledge_graph": graph_metadata(state),
        },
        metrics=RunMetrics(
            latency_ms=state.get("active_ms", 0), model_calls=state["model_calls"],
            tool_calls=state["tool_calls"], retrieved_documents=len(state["evidence"]),
            source_coverage=sum(
                claim.status == ClaimStatus.SUPPORTED_FACT and bool(claim.citations)
                for claim in claims
            ) / max(1, len(claims)),
        ),
    )
