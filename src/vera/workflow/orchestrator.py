from vera.config import Settings, get_settings
from vera.domain.graph import GraphTopology
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.memory.store import MemoryStore
from vera.providers.base import ModelProvider
from vera.providers.factory import build_provider
from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.embeddings import Embedder, build_embedder
from vera.retrieval.knowledge import CuratedKnowledge
from vera.retrieval.store import CorpusStore
from vera.routing.router import Router
from vera.sources.hub import SourceHub
from vera.workflow.graph import build_graph
from vera.workflow.runtime import Runtime
from vera.workflow.topology import build_topology


class VeraOrchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        provider: ModelProvider | None = None,
        embedder: Embedder | None = None,
        sources: SourceHub | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        selected_embedder = embedder or build_embedder(self.settings)
        selected_provider = provider or build_provider(self.settings)
        knowledge = CuratedKnowledge()
        corpus_store = CorpusStore(
            self.settings.corpus_dir,
            self.settings.max_corpus_documents,
        )
        self.runtime = Runtime(
            settings=self.settings,
            embedder=selected_embedder,
            knowledge=knowledge,
            corpus=LocalCorpus(
                selected_embedder,
                corpus_store,
                self.settings.retrieval_min_score,
            ),
            sources=sources or SourceHub(self.settings),
            provider=selected_provider,
            router=Router(selected_provider, knowledge.supports),
            memory=MemoryStore(self.settings.db_path, selected_embedder),
        )
        self.graph = build_graph(self.runtime)

    def analyze(self, request: AnalysisRequest | dict) -> AnalysisResult:
        normalized = (
            request
            if isinstance(request, AnalysisRequest)
            else AnalysisRequest.model_validate(request)
        )
        if len(normalized.events) > self.settings.max_events:
            raise ValueError(f"Request exceeds the {self.settings.max_events} event limit")
        state = self.graph.invoke({"request": normalized})
        return state["result"]

    def get_run(self, run_id: str) -> AnalysisResult | None:
        return self.runtime.memory.get_run(run_id)

    def list_runs(self, limit: int = 20) -> list[AnalysisResult]:
        return self.runtime.memory.list_runs(limit)

    def get_topology(self, run_id: str | None = None) -> GraphTopology | None:
        selected = self.get_run(run_id) if run_id else None
        if run_id and selected is None:
            return None
        return build_topology(self.graph, selected, self.list_runs(20))
