from langgraph.graph import END, START, StateGraph

from vera.domain.enums import Route
from vera.domain.state import GraphState
from vera.workflow.acquisition import ContextAcquirer
from vera.workflow.nodes import WorkflowNodes
from vera.workflow.react import ReActEvidenceNodes
from vera.workflow.review import ReviewNodes
from vera.workflow.runtime import Runtime


def build_graph(runtime: Runtime, *, checkpointer=None, review_enabled: bool = True):
    nodes = WorkflowNodes(runtime)
    review = ReviewNodes(runtime, enabled=review_enabled)
    acquisition = ContextAcquirer(runtime)
    graph = StateGraph(GraphState)
    graph.add_node("initialize", nodes.initialize)
    graph.add_node("route", nodes.route)
    graph.add_node("cag", acquisition.cag)
    graph.add_node("rag", acquisition.rag)
    graph.add_node("tools", acquisition.tools)
    graph.add_node("stream", acquisition.stream)
    graph.add_node("full", acquisition.full)
    graph.add_node("generate", nodes.generate)
    graph.add_node("validate", nodes.validate)
    graph.add_node("reflection", nodes.reflection)
    graph.add_node("review_assess", review.assess)
    graph.add_node("review_wait", review.wait)
    graph.add_node("revise", review.revise)
    graph.add_node("finalize", nodes.finalize)
    if runtime.settings.react_enabled:
        react_nodes = ReActEvidenceNodes(runtime)
        graph.add_node("react_decide", react_nodes.decide)
        graph.add_node("react_execute", react_nodes.execute)

    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "route")
    graph.add_conditional_edges(
        "route",
        lambda state: state["route"],
        {
            Route.CAG_ONLY: "cag",
            Route.CAG_RAG: "rag",
            Route.CAG_RAG_TOOL: "tools",
            Route.STREAM: "stream",
            Route.FULL: "full",
        },
    )
    for node in ("cag", "rag", "tools", "stream", "full"):
        graph.add_edge(node, "react_decide" if runtime.settings.react_enabled else "generate")
    if runtime.settings.react_enabled:
        graph.add_conditional_edges(
            "react_decide",
            lambda state: "finish" if state["react_action"].action == "finish" else "execute",
            {"finish": "generate", "execute": "react_execute"},
        )
        graph.add_edge("react_execute", "react_decide")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges(
        "validate",
        lambda state: "retry" if state["retry_generation"] else "continue",
        {"retry": "generate", "continue": "reflection"},
    )
    graph.add_edge("reflection", "review_assess")
    graph.add_conditional_edges(
        "review_assess",
        lambda state: "review" if state["review_required"] else "continue",
        {"review": "review_wait", "continue": "finalize"},
    )
    graph.add_conditional_edges(
        "review_wait",
        lambda state: state["review_action"],
        {"approve": "finalize", "reject": END, "revise": "revise"},
    )
    graph.add_conditional_edges(
        "revise",
        lambda state: "error" if state.get("revision_error") else "continue",
        {"error": "review_assess", "continue": "validate"},
    )
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
