from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

from vera.config import Settings
from vera.domain.evidence import Evidence
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.errors import VeraError
from vera.knowledge_graph.models import GraphStatus
from vera.knowledge_graph.projection import put_record, put_run
from vera.knowledge_graph.schema import TABLES, VERSION, check_version, migrate

_LOCKS: dict[str, RLock] = {}
_GUARD = RLock()


class KnowledgeGraphError(VeraError):
    """A local graph operation failed; callers can retain ordinary retrieval."""


class KnowledgeGraphStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.kg_path.resolve()
        with _GUARD:
            self.lock = _LOCKS.setdefault(str(self.path), RLock())

    @contextmanager
    def connection(self, *, write: bool = False, create: bool = False) -> Iterator:
        with self.lock:
            db = conn = None
            try:
                import kuzu

                if not create and not self.path.is_file():
                    raise KnowledgeGraphError("Knowledge graph is absent; run vera kg-build")
                if create:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                db = kuzu.Database(
                    self.path,
                    buffer_pool_size=64 * 1024 * 1024,
                    max_num_threads=2,
                    read_only=not write,
                )
                conn = kuzu.Connection(db, num_threads=2)
                conn.set_query_timeout(self.settings.kg_query_timeout_ms)
                if create:
                    migrate(conn)
                else:
                    check_version(conn)
                yield conn
            except ImportError as exc:
                raise KnowledgeGraphError(
                    "Install Kuzu with uv sync --extra knowledge-graph"
                ) from exc
            except KnowledgeGraphError:
                raise
            except (RuntimeError, ValueError, OSError, KeyError, TypeError) as exc:
                raise KnowledgeGraphError(f"Kuzu operation failed: {exc}") from exc
            finally:
                if conn is not None:
                    conn.close()
                if db is not None:
                    db.close()

    def build(self, documents: list[Evidence]) -> GraphStatus:
        if len(documents) > self.settings.max_corpus_documents:
            raise KnowledgeGraphError("Graph import exceeds the document limit")
        with self.connection(write=True, create=True) as conn, transaction(conn):
            for document in documents:
                put_record(conn, document)
            # Preserve immutable versions, sharing descriptive links for identical source text.
            conn.execute(
                "MATCH (old:SourceRecord), (current:SourceRecord)-[:DESCRIBES]->(e:Entity) "
                "WHERE old.evidence_id = current.evidence_id AND old.source = current.source "
                "AND old.content = current.content "
                "AND (old.url = current.url OR (old.url IS NULL AND current.url IS NULL)) "
                "MERGE (old)-[:DESCRIBES]->(e)"
            ).close()
        return self.status()

    def project_run(self, request: AnalysisRequest, result: AnalysisResult) -> None:
        with self.connection(write=True) as conn, transaction(conn):
            put_run(conn, request, result)

    def status(self) -> GraphStatus:
        status = GraphStatus(path=str(self.path))
        try:
            with self.connection() as conn:
                status.counts = {
                    table: conn.execute(f"MATCH (n:{table}) RETURN count(n)").get_next()[0]
                    for table in TABLES
                }
            status.available = True
            status.schema_version = VERSION
        except KnowledgeGraphError as exc:
            status.error = str(exc)
        return status


@contextmanager
def transaction(connection) -> Iterator[None]:
    connection.execute("BEGIN TRANSACTION").close()
    try:
        yield
        connection.execute("COMMIT").close()
    except Exception:
        connection.execute("ROLLBACK").close()
        raise
