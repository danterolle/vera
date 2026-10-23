import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

CHECKPOINT_MODELS = [
    ("vera.domain.actions", "ReActAction"),
    ("vera.domain.actions", "ReActObservation"),
    ("vera.domain.enums", "Route"),
    ("vera.domain.enums", "SourceType"),
    ("vera.domain.enums", "EvidenceStatus"),
    ("vera.domain.enums", "ClaimStatus"),
    ("vera.domain.enums", "Severity"),
    ("vera.domain.evidence", "Evidence"),
    ("vera.domain.evidence", "Claim"),
    ("vera.domain.evidence", "Citation"),
    ("vera.domain.plans", "ResourcePlan"),
    ("vera.domain.reports", "AnalysisResult"),
    ("vera.domain.reports", "DetectionAlert"),
    ("vera.domain.reports", "GeneratedAnswer"),
    ("vera.domain.reports", "IncidentReport"),
    ("vera.domain.reports", "ReflectionReport"),
    ("vera.domain.reports", "RunMetrics"),
    ("vera.domain.reports", "StreamStatistics"),
    ("vera.domain.requests", "AnalysisRequest"),
    ("vera.domain.requests", "NetworkEvent"),
]


@contextmanager
def sqlite_checkpointer(path: Path) -> Iterator[SqliteSaver]:
    with closing(sqlite3.connect(path, timeout=10, check_same_thread=False)) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")
        yield SqliteSaver(
            connection, serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_MODELS)
        )
