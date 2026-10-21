from vera.domain.review import ReviewRecord, ReviewStatus
from vera.errors import ReviewUnavailable
from vera.memory.store import MemoryStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    review_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE TABLE IF NOT EXISTS review_actions (
    run_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    action TEXT NOT NULL,
    version INTEGER NOT NULL,
    feedback TEXT,
    response_json TEXT,
    PRIMARY KEY (run_id, decision_id),
    FOREIGN KEY (run_id) REFERENCES reviews(run_id)
);
"""


class ReviewStore:
    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        with memory._connect() as connection:
            connection.executescript(SCHEMA)

    def add(self, record: ReviewRecord) -> ReviewRecord:
        with self.memory._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO reviews VALUES (?, ?, ?, ?)",
                (record.run_id, record.status.value, record.version, record.model_dump_json()),
            )
        stored = self.get(record.run_id)
        if stored is None:
            raise ReviewUnavailable("Could not persist the pending review")
        return stored

    def get(self, run_id: str) -> ReviewRecord | None:
        with self.memory._connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM reviews WHERE run_id = ?", (run_id,)
            ).fetchone()
        return ReviewRecord.model_validate_json(row["review_json"]) if row else None

    def list_open(self) -> list[ReviewRecord]:
        with self.memory._connect() as connection:
            rows = connection.execute(
                "SELECT review_json FROM reviews "
                "WHERE status IN (?, ?, ?) ORDER BY rowid DESC",
                (
                    ReviewStatus.PENDING.value,
                    ReviewStatus.PROCESSING.value,
                    ReviewStatus.ERROR.value,
                ),
            ).fetchall()
        return [ReviewRecord.model_validate_json(row["review_json"]) for row in rows]

    def set_error(self, run_id: str, message: str) -> None:
        record = self.get(run_id)
        if record is None:
            return
        updated = record.model_copy(update={"status": ReviewStatus.ERROR, "error": message})
        with self.memory._connect() as connection:
            connection.execute(
                "UPDATE reviews SET status = ?, review_json = ? "
                "WHERE run_id = ? AND status IN (?, ?)",
                (
                    ReviewStatus.ERROR.value,
                    updated.model_dump_json(),
                    run_id,
                    ReviewStatus.PROCESSING.value,
                    ReviewStatus.PENDING.value,
                ),
            )
