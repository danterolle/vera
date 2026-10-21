import asyncio
import json

import httpx
import pytest
from typer.testing import CliRunner

from vera.domain.requests import AnalysisRequest, NetworkEvent
from vera.interfaces.api import create_app
from vera.interfaces.cli import app
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.memory.graph_jobs import project_pending
from vera.retrieval.knowledge import CuratedKnowledge
from vera.workflow.orchestrator import VeraOrchestrator

pytest.importorskip("kuzu")


@pytest.fixture
def engine(settings):
    enabled = settings.model_copy(
        update={"kg_enabled": True, "kg_path": settings.db_path.with_suffix(".kuzu")}
    )
    engine = VeraOrchestrator(enabled)
    engine.runtime.knowledge_graph.build(
        CuratedKnowledge().documents + engine.runtime.corpus.documents
    )
    return engine


@pytest.mark.parametrize("query", ["Explain MITRE ATT&CK T1059.001", "Explain PowerShell"])
def test_workflow_uses_graph_even_when_lexical_retrieval_has_no_results(engine, monkeypatch, query):
    monkeypatch.setattr(engine.runtime.corpus, "search", lambda *args: [])
    result = engine.analyze(AnalysisRequest(query=query))
    report = result.metadata["knowledge_graph"]
    assert report["attempted"] and report["available"]
    assert "attack:enterprise:T1059" in report["entity_ids"]
    assert report["assertion_ids"] and report["cited_evidence_ids"]
    assert report["projection"] == "complete"
    registry = {record.id: record for record in result.evidence}
    for claim in result.claims:
        for citation in claim.citations:
            assert citation.supporting_quote in registry[citation.evidence_id].content
    assert engine.get_run(result.run_id).metadata["knowledge_graph"] == report


def test_disabled_graph_preserves_existing_workflow(settings):
    result = VeraOrchestrator(settings).analyze(AnalysisRequest(query="Explain MITRE ATT&CK T1190"))
    assert not result.metadata["knowledge_graph"]["enabled"]
    assert not any(item.id.startswith("ev-kg-") for item in result.evidence)


def test_missing_graph_falls_back_and_projection_retries(settings):
    enabled = settings.model_copy(
        update={"kg_enabled": True, "kg_path": settings.db_path.with_suffix(".kuzu")}
    )
    engine = VeraOrchestrator(enabled)
    result = engine.analyze(AnalysisRequest(query="Explain MITRE ATT&CK T1190"))
    assert result.answer and result.warnings
    assert result.metadata["knowledge_graph"]["projection"] == "pending"
    assert engine.get_run(result.run_id).warnings == result.warnings
    graph = engine.runtime.knowledge_graph
    graph.build(engine.runtime.corpus.documents)
    assert project_pending(engine.runtime.memory, graph) == 1
    assert project_pending(engine.runtime.memory, graph) == 0
    assert graph.status().counts["Run"] == 1
    assert engine.get_run(result.run_id).metadata["knowledge_graph"]["projection"] == "complete"


def test_simulated_alerts_and_original_event_indexes_are_persisted(engine):
    events = [
        NetworkEvent(
            src_ip="192.0.2.1",
            dst_ip="192.0.2.2",
            protocol="HTTP",
            dst_port=80,
            http_status=401,
            simulated=True,
        )
        for _ in range(5)
    ]
    request = AnalysisRequest(query="Analyze this stream", events=events, simulated=True)
    result = engine.analyze(request)
    graph = engine.runtime.knowledge_graph
    before = graph.status().counts
    graph.project_run(request, result)
    assert graph.status().counts == before
    with graph.connection() as conn:
        assert conn.execute("MATCH (a:Alert) RETURN a.status").get_all() == [["simulated"]]
        assert conn.execute("MATCH ()-[r:SUGGESTS]->() RETURN r.status").get_all() == [
            ["simulated"]
        ]
        assert conn.execute("MATCH (e:Event) RETURN count(e)").get_next() == [5]


def test_knowledge_graph_page_api_and_bounds(engine):
    async def exercise():
        transport = httpx.ASGITransport(app=create_app(orchestrator=engine))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            page = await client.get("/knowledge-graph")
            assert page.status_code == 200 and "Knowledge graph" in page.text
            assert "default-src 'self'" in page.headers["content-security-policy"]
            for name in ("knowledge.js", "knowledge.css"):
                assert (await client.get(f"/assets/{name}")).status_code == 200
            view = (await client.get("/v1/knowledge-graph?id=T1059.001")).json()
            assert view["status"]["available"] and view["edges"]
            assert all(node["kind"] not in {"assertion", "source"} for node in view["nodes"])
            assert any(edge["predicate"] == "subtechnique_of" for edge in view["edges"])
            raw = (await client.get("/v1/knowledge-graph?id=PowerShell&provenance=true")).json()
            assert any(node["kind"] == "assertion" for node in raw["nodes"])
            matches = (await client.get("/v1/knowledge-graph/search?q=Power")).json()
            assert any(item["id"] == "attack:enterprise:T1059.001" for item in matches)
            assert (await client.get("/v1/knowledge-graph?limit=101")).status_code == 422
            assert (await client.get("/v1/knowledge-graph?id=arbitrary")).json()["nodes"] == []
            assert (await client.get("/v1/knowledge-graph/status")).json()["counts"]["Entity"] > 0

    asyncio.run(exercise())


def test_cli_build_status_export_are_incremental(settings, monkeypatch, tmp_path):
    monkeypatch.setenv("VERA_DB_PATH", str(settings.db_path))
    monkeypatch.setenv("VERA_KG_PATH", str(settings.db_path.with_suffix(".kuzu")))
    monkeypatch.setenv("VERA_CORPUS_DIR", str(settings.corpus_dir))
    runner = CliRunner()
    initial = runner.invoke(app, ["kg-status"])
    assert initial.exit_code == 1
    first = runner.invoke(app, ["kg-build"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["kg-build"])
    assert second.exit_code == 0, second.output
    assert json.loads(first.output)["counts"] == json.loads(second.output)["counts"]
    target = tmp_path / "view.json"
    exported = runner.invoke(app, ["kg-export", "--id", "T1059.001", "--output", str(target)])
    assert exported.exit_code == 0, exported.output
    assert json.loads(target.read_text())["edges"]
    assert (
        KnowledgeGraphStore(
            settings.model_copy(update={"kg_path": settings.db_path.with_suffix(".kuzu")})
        )
        .status()
        .available
    )
