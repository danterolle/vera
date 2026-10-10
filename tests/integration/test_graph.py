import asyncio

import httpx

from vera.domain.enums import Route
from vera.domain.requests import AnalysisRequest
from vera.interfaces.api import create_app
from vera.workflow.orchestrator import VeraOrchestrator


def test_compiled_topology_and_execution_highlight(settings) -> None:
    orchestrator = VeraOrchestrator(settings)
    topology = orchestrator.get_topology()
    assert topology is not None
    assert len(topology.nodes) == 13
    assert len(topology.edges) == 17
    assert "graph TD" in topology.mermaid
    assert not any(node.active for node in topology.nodes)

    result = orchestrator.analyze(AnalysisRequest(query="What is least privilege?"))
    executed = orchestrator.get_topology(result.run_id)
    assert executed is not None
    active = {node.id for node in executed.nodes if node.active}
    assert {"initialize", "route", "cag", "generate", "finalize"} <= active
    assert "rag" not in active
    assert executed.selected_run_id == result.run_id
    assert executed.recent_runs[0].route == Route.CAG_ONLY
    assert executed.execution is not None
    assert executed.execution.route == Route.CAG_ONLY
    route_node = next(node for node in executed.nodes if node.id == "route")
    assert route_node.label == "Meta-controller"
    assert route_node.input_contract
    assert route_node.output_contract


def test_graph_browser_and_api(settings) -> None:
    orchestrator = VeraOrchestrator(settings)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=create_app(orchestrator=orchestrator))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            page = await client.get("/graph")
            assert page.status_code == 200
            assert "default-src 'self'" in page.headers["content-security-policy"]
            assert "Workflow explorer" in page.text
            assert "Preview a route" in page.text
            assert (await client.get("/assets/graph.js")).status_code == 200
            assert (await client.get("/assets/graph-ui.css")).status_code == 200
            assert (await client.get("/assets/graph-svg.css")).status_code == 200
            assert (await client.get("/assets/graph-panels.js")).status_code == 200
            assert (await client.get("/assets/graph-renderer.js")).status_code == 200
            assert (await client.get("/assets/graph-viewport.js")).status_code == 200
            graph = await client.get("/v1/graph")
            assert graph.status_code == 200
            assert len(graph.json()["nodes"]) == 13
            assert (await client.get("/v1/graph?run_id=missing")).status_code == 404

    asyncio.run(exercise())
