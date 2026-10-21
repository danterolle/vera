from uuid import UUID

from vera.domain.reports import AnalysisResult
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.errors import ReviewConflict
from vera.memory.reviews import ReviewStore


class ReviewDecisions:
    def __init__(self, reviews: ReviewStore) -> None:
        self.reviews = reviews

    def claim(
        self, run_id: str, decision: ReviewDecision, *, revision_supported: bool = True
    ) -> str | None:
        with self.reviews.memory._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, version, review_json FROM reviews WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            previous = connection.execute(
                "SELECT action, version, feedback, response_json FROM review_actions "
                "WHERE run_id = ? AND decision_id = ?",
                (run_id, str(decision.decision_id)),
            ).fetchone()
            if previous:
                if (
                    previous["action"] != decision.action
                    or previous["version"] != decision.version
                    or previous["feedback"] != decision.feedback
                ):
                    raise ReviewConflict("This decision ID was used with different input")
                if previous["response_json"] is not None:
                    return previous["response_json"]
                if decision.action == "revise" and not revision_supported:
                    raise ReviewConflict("Revision requires an external model provider")
                if row["status"] != ReviewStatus.ERROR:
                    raise ReviewConflict("This decision is already in progress")
            else:
                if row["status"] != ReviewStatus.PENDING:
                    raise ReviewConflict("This review is not pending")
                if row["version"] != decision.version:
                    raise ReviewConflict("The review changed; refresh before deciding")
                if decision.action == "revise" and not revision_supported:
                    raise ReviewConflict("Revision requires an external model provider")
                record = ReviewRecord.model_validate_json(row["review_json"])
                if decision.action == "revise" and record.revision_count >= 2:
                    raise ReviewConflict("The two revision cycles have been used")
                connection.execute(
                    "INSERT INTO review_actions VALUES (?, ?, ?, ?, ?, NULL)",
                    (
                        run_id, str(decision.decision_id), decision.action,
                        decision.version, decision.feedback,
                    ),
                )
            record = ReviewRecord.model_validate_json(row["review_json"])
            processing = record.model_copy(
                update={"status": ReviewStatus.PROCESSING, "error": None}
            )
            connection.execute(
                "UPDATE reviews SET status = ?, review_json = ? WHERE run_id = ?",
                (ReviewStatus.PROCESSING.value, processing.model_dump_json(), run_id),
            )
        return None

    def finish(
        self,
        decision: ReviewDecision,
        record: ReviewRecord,
        response: ReviewRecord | AnalysisResult,
    ) -> None:
        with self.reviews.memory._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE reviews SET status = ?, version = ?, review_json = ? "
                "WHERE run_id = ? AND status IN (?, ?)",
                (
                    record.status.value, record.version, record.model_dump_json(),
                    record.run_id, ReviewStatus.PROCESSING.value, ReviewStatus.ERROR.value,
                ),
            )
            if changed.rowcount != 1:
                raise ReviewConflict("Review status changed during the decision")
            changed = connection.execute(
                "UPDATE review_actions SET response_json = ? "
                "WHERE run_id = ? AND decision_id = ? AND response_json IS NULL",
                (response.model_dump_json(), record.run_id, str(decision.decision_id)),
            )
            if changed.rowcount != 1:
                raise ReviewConflict("Decision status changed during finalization")

    def unfinished(self, run_id: str) -> ReviewDecision | None:
        with self.reviews.memory._connect() as connection:
            row = connection.execute(
                "SELECT decision_id, action, version, feedback FROM review_actions "
                "WHERE run_id = ? AND response_json IS NULL",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return ReviewDecision(
            decision_id=UUID(row["decision_id"]),
            action=row["action"],
            version=row["version"],
            feedback=row["feedback"],
        )
