from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.memory.store import MemoryStore


def project_pending(
    memory: MemoryStore, graph: KnowledgeGraphStore, *, replay: bool = False
) -> int:
    projected = 0
    cursor = ""
    while True:
        with memory._connect() as conn:
            rows = conn.execute(
                "SELECT j.run_id, j.request_json, r.result_json FROM graph_jobs j "
                "JOIN runs r ON r.id = j.run_id "
                "WHERE (? OR j.projected = 0) AND j.run_id > ? ORDER BY j.run_id LIMIT 20",
                (replay, cursor),
            ).fetchall()
        if not rows:
            return projected
        for row in rows:
            graph.project_run(
                AnalysisRequest.model_validate_json(row["request_json"]),
                AnalysisResult.model_validate_json(row["result_json"]),
            )
            with memory._connect() as conn:
                conn.execute(
                    "UPDATE graph_jobs SET projected = 1 WHERE run_id = ?", (row["run_id"],)
                )
                result = AnalysisResult.model_validate_json(row["result_json"])
                result.metadata.setdefault("knowledge_graph", {})["projection"] = "complete"
                conn.execute(
                    "UPDATE runs SET result_json = ? WHERE id = ?",
                    (
                        result.model_dump_json(),
                        row["run_id"],
                    ),
                )
            cursor = row["run_id"]
            projected += 1
