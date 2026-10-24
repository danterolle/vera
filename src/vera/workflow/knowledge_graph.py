from vera.domain.reports import AnalysisResult
from vera.domain.state import GraphState
from vera.knowledge_graph.store import KnowledgeGraphError
from vera.memory.graph_jobs import project_pending
from vera.workflow.runtime import Runtime


def graph_metadata(state: GraphState) -> dict:
    report = dict(state.get("knowledge_graph", {"enabled": False, "attempted": False}))
    report["cited_evidence_ids"] = sorted(
        {
            citation.evidence_id
            for claim in state["draft"].claims
            for citation in claim.citations
            if citation.evidence_id in report.get("retained_evidence_ids", [])
        }
    )
    return report


def persist_result(runtime: Runtime, state: GraphState, result: AnalysisResult) -> None:
    graph = (
        runtime.knowledge_graph if state["resource_plan"].intent == "cybersecurity" else None
    )
    if graph is not None:
        result.metadata["knowledge_graph"]["projection"] = "pending"
    runtime.memory.save(state["request"], result, graph_projection=graph is not None)
    if graph is None:
        return
    try:
        project_pending(runtime.memory, graph)
        result.metadata["knowledge_graph"]["projection"] = "complete"
    except KnowledgeGraphError as exc:
        result.warnings.append(f"Graph projection pending: {exc}")
    with runtime.memory._connect() as conn:
        conn.execute(
            "UPDATE runs SET result_json = ? WHERE id = ?",
            (
                result.model_dump_json(),
                result.run_id,
            ),
        )
