from collections import Counter
from typing import Any

from vera.domain.enums import Route
from vera.domain.graph import GraphEdge, GraphExecution, GraphNode, GraphRun, GraphTopology
from vera.domain.reports import AnalysisResult
from vera.workflow.node_catalog import NODE_DETAILS, NODE_LABELS, POSITIONS

ROUTE_NODE = {
    Route.CAG_ONLY: "cag",
    Route.CAG_RAG: "rag",
    Route.CAG_RAG_TOOL: "tools",
    Route.STREAM: "stream",
    Route.FULL: "full",
}


def build_topology(
    compiled_graph: Any,
    selected_run: AnalysisResult | None,
    recent_runs: list[AnalysisResult],
) -> GraphTopology:
    graph = compiled_graph.get_graph()
    active, executions = _execution_state(selected_run)
    nodes = [
        _node(node_id, node.name, active, executions)
        for node_id, node in graph.nodes.items()
    ]
    edges = [
        GraphEdge(
            source=edge.source,
            target=edge.target,
            label=_label(edge.data),
            conditional=edge.conditional,
            active=_edge_active(edge.source, edge.target, active, executions),
        )
        for edge in graph.edges
    ]
    return GraphTopology(
        selected_run_id=selected_run.run_id if selected_run else None,
        nodes=nodes,
        edges=edges,
        mermaid=graph.draw_mermaid(),
        recent_runs=[
            GraphRun(run_id=run.run_id, route=run.route, created_at=run.created_at)
            for run in recent_runs
        ],
        execution=_execution(selected_run),
    )


def _node(
    node_id: str,
    name: str,
    active: set[str],
    executions: Counter[str],
) -> GraphNode:
    category, description, input_contract, output_contract = NODE_DETAILS.get(
        node_id,
        ("Workflow", "LangGraph node.", "Graph state", "Updated graph state"),
    )
    x, y = POSITIONS.get(node_id, (600, 450))
    label = NODE_LABELS.get(node_id, name)
    return GraphNode(
        id=node_id,
        label=label,
        category=category,
        description=description,
        input_contract=input_contract,
        output_contract=output_contract,
        x=x,
        y=y,
        active=node_id in active,
        executions=executions[node_id],
    )


def _execution(result: AnalysisResult | None) -> GraphExecution | None:
    if result is None:
        return None
    sources = {item.source for item in result.evidence}
    return GraphExecution(
        route=result.route,
        latency_ms=result.metrics.latency_ms,
        model_calls=result.metrics.model_calls,
        tool_calls=result.metrics.tool_calls,
        evidence_documents=result.metrics.retrieved_documents,
        source_count=len(sources),
        completeness=result.reflection.completeness_score,
        warning_count=len(result.warnings),
    )


def _execution_state(result: AnalysisResult | None) -> tuple[set[str], Counter[str]]:
    if result is None:
        return set(), Counter()
    branch = ROUTE_NODE[result.route]
    active = {
        "__start__",
        "initialize",
        "route",
        branch,
        "generate",
        "validate",
        "reflection",
        "finalize",
        "__end__",
    }
    executions = Counter({node: 1 for node in active})
    executions["generate"] = sum(item.startswith("generation:") for item in result.trace)
    executions["validate"] = sum(item.startswith("validation:") for item in result.trace)
    return active, executions


def _edge_active(
    source: str,
    target: str,
    active: set[str],
    executions: Counter[str],
) -> bool:
    if source == "route":
        return target in active
    if target == "generate" and source in ROUTE_NODE.values():
        return source in active
    if source == "validate" and target == "generate":
        return executions["generate"] > 1
    return source in active and target in active


def _label(value: Any) -> str:
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)
