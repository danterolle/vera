from collections import Counter

from vera.domain.evidence import Evidence
from vera.retrieval.embeddings import Embedder, cosine_similarity
from vera.retrieval.models import CorpusStatus
from vera.retrieval.ranking import Bm25Ranker, normalize
from vera.retrieval.resources import load_evidence_directory
from vera.retrieval.store import CorpusStore


class LocalCorpus:
    def __init__(
        self,
        embedder: Embedder,
        store: CorpusStore | None = None,
        min_score: float = 0.05,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.min_score = min_score
        self.bundled_documents = load_evidence_directory("corpus")
        synchronized = store.load() if store else []
        self.synchronized_documents = len(synchronized)
        self.documents = list(
            {item.id: item for item in self.bundled_documents + synchronized}.values()
        )
        texts = [self._searchable_text(document) for document in self.documents]
        self._vectors = embedder.embed(texts)
        self._lexical = Bm25Ranker(self.documents)

    def search(self, query: str, limit: int = 5) -> list[Evidence]:
        query_vector = self.embedder.embed([query])[0]
        vector_scores = [
            max(0.0, cosine_similarity(query_vector, vector)) for vector in self._vectors
        ]
        lexical_scores = self._lexical.scores(query)
        vectors = vector_scores
        lexical = normalize(lexical_scores)
        ranked = sorted(
            (
                (0.7 * lexical[index] + 0.3 * vectors[index], index, document)
                for index, document in enumerate(self.documents)
            ),
            key=lambda item: (-item[0], item[2].title),
        )
        results: list[Evidence] = []
        for score, index, document in ranked:
            if score < self.min_score or len(results) >= limit:
                break
            metadata = {
                **document.metadata,
                "retrieval_score": round(score, 4),
                "lexical_score": round(lexical[index], 4),
                "vector_score": round(vectors[index], 4),
            }
            results.append(document.model_copy(update={"metadata": metadata}))
        return results

    def status(self) -> CorpusStatus:
        counts = Counter(item.source.value for item in self.documents)
        return CorpusStatus(
            bundled_documents=len(self.bundled_documents),
            synchronized_documents=self.synchronized_documents,
            total_documents=len(self.documents),
            by_source=dict(sorted(counts.items())),
            feeds=self.store.manifests() if self.store else [],
        )

    @staticmethod
    def _searchable_text(document: Evidence) -> str:
        keywords = " ".join(document.metadata.get("keywords", []))
        return f"{document.title} {document.content} {keywords}"
