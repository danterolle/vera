import time

from vera.domain.enums import ClaimStatus
from vera.domain.reports import AnalysisResult, RunMetrics
from vera.domain.state import GraphState
from vera.providers.rendering import render_answer
from vera.workflow.knowledge_graph import graph_metadata, persist_result
from vera.workflow.runtime import Runtime


def finalize_result(runtime: Runtime, state: GraphState) -> dict:
    claims = state["draft"].claims
    factual = [claim for claim in claims if claim.status == ClaimStatus.SUPPORTED_FACT]
    assessable = [
        claim for claim in claims
        if claim.status in {ClaimStatus.SUPPORTED_FACT, ClaimStatus.SYSTEM_INFERENCE}
    ]
    hidden_failures = max(
        0,
        state["reflection"].grounding_failures
        - sum(claim.status == ClaimStatus.SYSTEM_INFERENCE for claim in claims),
    )
    grounded = sum(bool(claim.citations) for claim in factual)
    denominator = len(assessable) + hidden_failures
    coverage = grounded / denominator if denominator else 1.0
    trace = state["trace"] + ["persistence:sqlite"]
    metadata = {
        "provider": runtime.provider.name,
        "model": runtime.settings.llm_model if runtime.provider.external else None,
        "provider_fallback": state["provider_fallback"],
        "out_of_scope": state["draft"].out_of_scope,
        "embedding_backend": runtime.embedder.name,
        "route_reason": state["route_reason"],
        "resource_plan": state["resource_plan"].model_dump(mode="json"),
        "knowledge_graph": graph_metadata(state),
    }
    if runtime.settings.react_enabled:
        metadata["react_enabled"] = True
        metadata["model_call_limit"] = runtime.settings.model_call_limit
        metadata["react_steps"] = state["react_steps"]
        metadata["generation_attempts"] = state["generation_attempts"]
        metadata["react_observations"] = [
            item.model_dump(mode="json") for item in state["react_observations"]
        ]
    if state.get("review_required"):
        metadata["human_review"] = {
            "decision": "approved",
            "revision_count": state.get("revision_count", 0),
        }
    result = AnalysisResult(
        run_id=state["run_id"],
        route=state["route"],
        answer=render_answer(
            state["draft"].summary, claims, state["evidence"], state["incident"]
        ),
        claims=claims,
        evidence=state["evidence"],
        incident=state["incident"],
        reflection=state["reflection"],
        metrics=RunMetrics(
            latency_ms=state.get("active_ms", 0.0)
            + (time.perf_counter() - state["started_at"]) * 1000,
            model_calls=state["model_calls"],
            tool_calls=state["tool_calls"],
            retrieved_documents=len(state["evidence"]),
            source_coverage=round(coverage, 3),
        ),
        trace=trace,
        warnings=state["warnings"],
        metadata=metadata,
    )
    persist_result(runtime, state, result)
    return {"result": result, "trace": trace}
