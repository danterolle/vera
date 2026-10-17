from dataclasses import dataclass

from vera.config import Settings
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.memory.store import MemoryStore
from vera.providers.base import ModelProvider
from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.embeddings import Embedder
from vera.retrieval.knowledge import CuratedKnowledge
from vera.routing.router import Router
from vera.sources.hub import SourceHub


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    embedder: Embedder
    knowledge: CuratedKnowledge
    corpus: LocalCorpus
    sources: SourceHub
    provider: ModelProvider
    router: Router
    memory: MemoryStore
    knowledge_graph: KnowledgeGraphStore | None = None
