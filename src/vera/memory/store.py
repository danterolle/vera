import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.retrieval.embeddings import Embedder, cosine_similarity

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, session_id TEXT, query TEXT NOT NULL, route TEXT NOT NULL,
    result_json TEXT NOT NULL, latency_ms REAL NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    run_id TEXT NOT NULL, evidence_id TEXT NOT NULL, source TEXT NOT NULL,
    status TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id), FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS reflections (
    run_id TEXT PRIMARY KEY, report_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL,
    embedding_json TEXT NOT NULL, source_run_id TEXT NOT NULL,
    session_id TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (source_run_id) REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE TABLE IF NOT EXISTS graph_jobs (
    run_id TEXT PRIMARY KEY, request_json TEXT NOT NULL, projected INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
"""


class MemoryStore:
    def __init__(self, path: Path, embedder: Embedder) -> None:
        self.path = path
        self.embedder = embedder
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def save(
        self, request: AnalysisRequest, result: AnalysisResult, *, graph_projection: bool = False,
    ) -> None:
        created_at = result.created_at.isoformat()
        memories = self._memory_texts(request, result)
        vectors = self.embedder.embed([text for _, text in memories])
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result.run_id,
                    request.session_id,
                    request.query,
                    result.route.value,
                    result.model_dump_json(),
                    result.metrics.latency_ms,
                    created_at,
                ),
            )
            connection.executemany(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        result.run_id,
                        item.id,
                        item.source.value,
                        item.status.value,
                        item.title,
                        item.content,
                    )
                    for item in result.evidence
                ],
            )
            if graph_projection:
                connection.execute(
                    "INSERT INTO graph_jobs(run_id, request_json) VALUES (?, ?)",
                    (result.run_id, request.model_dump_json()),
                )
            connection.execute(
                "INSERT INTO reflections VALUES (?, ?)",
                (result.run_id, result.reflection.model_dump_json()),
            )
            connection.executemany(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(uuid4()),
                        kind,
                        text,
                        json.dumps(vector),
                        result.run_id,
                        request.session_id,
                        created_at,
                    )
                    for (kind, text), vector in zip(memories, vectors, strict=True)
                ],
            )

    def recall(self, query: str, limit: int, session_id: str | None = None) -> list[Evidence]:
        if limit == 0:
            return []
        vector = self.embedder.embed([query])[0]
        statement = (
            "SELECT id, kind, text, embedding_json, source_run_id, created_at "
            "FROM memories WHERE (? IS NULL OR session_id = ?) "
            "ORDER BY created_at DESC LIMIT 200"
        )
        with self._connect() as connection:
            rows = connection.execute(statement, (session_id, session_id)).fetchall()
        ranked = []
        for row in rows:
            candidate = json.loads(row["embedding_json"])
            if len(candidate) == len(vector):
                ranked.append((cosine_similarity(vector, candidate), row))
        ranked.sort(key=lambda item: (-item[0], item[1]["created_at"]))
        return [
            make_evidence(
                SourceType.MEMORY,
                f"Prior {row['kind']} memory",
                row["text"],
                metadata={
                    "memory_id": row["id"],
                    "source_run_id": row["source_run_id"],
                    "similarity": round(score, 4),
                },
            )
            for score, row in ranked[:limit]
            if score >= 0.15
        ]

    def get_run(self, run_id: str) -> AnalysisResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return AnalysisResult.model_validate_json(row["result_json"]) if row else None

    def list_runs(self, limit: int = 20) -> list[AnalysisResult]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT result_json FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [AnalysisResult.model_validate_json(row["result_json"]) for row in rows]

    @staticmethod
    def _memory_texts(
        request: AnalysisRequest,
        result: AnalysisResult,
    ) -> list[tuple[str, str]]:
        episode = (
            f"Request: {request.query}\nRoute: {result.route.value}\n"
            f"Outcome: {result.reflection.completeness_score:.2f} completeness."
        )
        supported = [
            claim.text for claim in result.claims if claim.status.value == "supported_fact"
        ]
        semantic = " ".join(supported)[:6000] or result.answer[:2000]
        return [("episodic", episode), ("semantic", semantic)]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                yield connection
