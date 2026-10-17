from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from vera import __version__
from vera.config import Settings
from vera.domain.graph import GraphTopology
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.errors import VeraError
from vera.interfaces.assets import load_asset, load_graph_page
from vera.knowledge_graph.models import GraphStatus, GraphView
from vera.knowledge_graph.search import search_entities
from vera.knowledge_graph.store import KnowledgeGraphError, KnowledgeGraphStore
from vera.knowledge_graph.view import graph_view
from vera.retrieval.models import CorpusStatus
from vera.workflow.orchestrator import VeraOrchestrator


def create_app(
    settings: Settings | None = None,
    orchestrator: VeraOrchestrator | None = None,
) -> FastAPI:
    engine = orchestrator or VeraOrchestrator(settings)
    application = FastAPI(
        title="VERA",
        version=__version__,
        description="Vulnerability Evidence and Reasoning Agent",
    )
    application.state.orchestrator = engine
    knowledge_store = engine.runtime.knowledge_graph or KnowledgeGraphStore(engine.settings)

    @application.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse(url="/graph")

    @application.get("/knowledge-graph", include_in_schema=False)
    def knowledge_page():
        return load_graph_page(knowledge=True)

    @application.get("/v1/knowledge-graph/status", response_model=GraphStatus)
    def knowledge_status() -> GraphStatus:
        return knowledge_store.status()

    @application.get("/v1/knowledge-graph/search")
    def knowledge_search(
        q: str = Query(min_length=2, max_length=200),
        limit: int = Query(default=12, ge=1, le=30),
    ) -> list[dict]:
        try:
            with knowledge_store.connection() as conn:
                return search_entities(conn, q, limit)
        except KnowledgeGraphError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/v1/knowledge-graph", response_model=GraphView)
    def knowledge_view(
        id: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=50, ge=1, le=100),
        provenance: bool = False,
    ) -> GraphView:
        try:
            return graph_view(knowledge_store, id, limit, provenance=provenance)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/health")
    def health() -> dict:
        corpus = engine.runtime.corpus.status()
        return {
            "status": "ok",
            "version": __version__,
            "provider": engine.runtime.provider.name,
            "model": engine.settings.llm_model if engine.runtime.provider.external else None,
            "knowledge_graph_enabled": engine.settings.kg_enabled,
            "embedding_backend": engine.runtime.embedder.name,
            "live_sources": engine.settings.live_sources,
            "corpus_documents": corpus.total_documents,
        }

    @application.post("/v1/analyze", response_model=AnalysisResult)
    def analyze(request: AnalysisRequest) -> AnalysisResult:
        try:
            return engine.analyze(request)
        except (VeraError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/graph", include_in_schema=False)
    def graph_page():
        return load_graph_page()

    @application.get("/assets/{name}", include_in_schema=False)
    def graph_asset(name: str):
        try:
            return load_asset(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Asset not found") from exc

    @application.get("/v1/graph", response_model=GraphTopology)
    def graph_topology(run_id: str | None = None) -> GraphTopology:
        topology = engine.get_topology(run_id)
        if topology is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return topology

    @application.get("/v1/corpus", response_model=CorpusStatus)
    def corpus_status() -> CorpusStatus:
        return engine.runtime.corpus.status()

    @application.get("/v1/runs", response_model=list[AnalysisResult])
    def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[AnalysisResult]:
        return engine.list_runs(limit)

    @application.get("/v1/runs/{run_id}", response_model=AnalysisResult)
    def get_run(run_id: str) -> AnalysisResult:
        result = engine.get_run(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result

    return application
