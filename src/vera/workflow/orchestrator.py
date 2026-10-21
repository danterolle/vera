from dataclasses import replace
from uuid import uuid4

from vera.config import Settings, get_settings
from vera.domain.graph import GraphTopology
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.domain.review import ReviewDecision, ReviewRecord
from vera.errors import ConfigurationError, ReviewUnavailable
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.memory.reviews import ReviewStore
from vera.memory.store import MemoryStore
from vera.providers.base import ModelProvider
from vera.providers.factory import build_provider
from vera.providers.react import ReActProvider
from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.embeddings import Embedder, build_embedder
from vera.retrieval.knowledge import CuratedKnowledge
from vera.retrieval.store import CorpusStore
from vera.routing.router import Router
from vera.sources.hub import SourceHub
from vera.workflow.checkpoints import sqlite_checkpointer
from vera.workflow.graph import build_graph
from vera.workflow.review_recovery import recover_reviews
from vera.workflow.review_service import ReviewService
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
        review_enabled: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        selected_embedder = embedder or build_embedder(self.settings)
        selected_provider = provider or build_provider(self.settings)
        if self.settings.react_enabled and (
            not selected_provider.external or not isinstance(selected_provider, ReActProvider)
        ):
            raise ConfigurationError("ReAct requires an external provider with action decisions")
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
            knowledge_graph=(
                KnowledgeGraphStore(self.settings) if self.settings.kg_enabled else None
            ),
        )
        self.reviews = ReviewStore(self.runtime.memory)
        self.checkpointer = sqlite_checkpointer(self.settings.db_path)
        self.graph = build_graph(
            self.runtime, checkpointer=self.checkpointer, review_enabled=review_enabled
        )
        self.review_service = ReviewService(self.runtime, self.graph, self.reviews)
        recover_reviews(self.checkpointer, self.review_service)

    def analyze(self, request: AnalysisRequest | dict) -> AnalysisResult | ReviewRecord:
        normalized = (
            request
            if isinstance(request, AnalysisRequest)
            else AnalysisRequest.model_validate(request)
        )
        if len(normalized.events) > self.settings.max_events:
            raise ValueError(f"Request exceeds the {self.settings.max_events} event limit")
        run_id = str(uuid4())
        config = self.review_service.config(
            run_id, recursion_limit=2 * self.settings.max_react_steps + 45
        )
        state = self.graph.invoke({"request": normalized, "run_id": run_id}, config=config)
        if "__interrupt__" in state:
            return self.review_service.register(run_id)
        if "result" not in state:
            raise ReviewUnavailable("Analysis ended without a report or review checkpoint")
        self.review_service.prune(run_id)
        return state["result"]

    def get_review(self, run_id: str) -> ReviewRecord | None:
        return self.review_service.get(run_id)

    def list_reviews(self) -> list[ReviewRecord]:
        return self.review_service.list_open()

    def decide_review(
        self, run_id: str, decision: ReviewDecision
    ) -> AnalysisResult | ReviewRecord:
        return self.review_service.decide(run_id, decision)

    def get_run(self, run_id: str) -> AnalysisResult | None:
        return self.runtime.memory.get_run(run_id)

    def list_runs(self, limit: int = 20) -> list[AnalysisResult]:
        return self.runtime.memory.list_runs(limit)

    def get_topology(self, run_id: str | None = None) -> GraphTopology | None:
        selected = self.get_run(run_id) if run_id else None
        if run_id and selected is None:
            return None
        graph = self.graph
        if selected and bool(selected.metadata.get("react_enabled")) != self.settings.react_enabled:
            historical_settings = self.settings.model_copy(
                update={"react_enabled": bool(selected.metadata.get("react_enabled"))}
            )
            graph = build_graph(replace(self.runtime, settings=historical_settings))
        return build_topology(graph, selected, self.list_runs(20))
