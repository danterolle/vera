from fastapi import FastAPI, HTTPException, Query

from vera import __version__
from vera.config import Settings
from vera.domain.graph import GraphTopology
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.errors import VeraError
from vera.interfaces.assets import load_asset, load_graph_page
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

    @application.get("/health")
    def health() -> dict:
        corpus = engine.runtime.corpus.status()
        return {
            "status": "ok",
            "version": __version__,
            "provider": engine.runtime.provider.name,
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
