import json
import logging
import sqlite3
import time
from typing import Any

from langgraph.types import Command

from vera.domain.reports import AnalysisResult
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.errors import ReviewUnavailable
from vera.memory.review_decisions import ReviewDecisions
from vera.memory.reviews import ReviewStore
from vera.workflow.provenance import STALE_DRAFT, has_current_validation
from vera.workflow.review_record import pending_review
from vera.workflow.runtime import Runtime

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, runtime: Runtime, graph: Any, reviews: ReviewStore) -> None:
        self.runtime = runtime
        self.graph = graph
        self.reviews = reviews
        self.decisions = ReviewDecisions(reviews)

    @staticmethod
    def config(run_id: str, recursion_limit: int = 60) -> dict:
        return {"configurable": {"thread_id": run_id}, "recursion_limit": recursion_limit}

    def snapshot(self, run_id: str):
        return self.graph.get_state(self.config(run_id))

    @staticmethod
    def is_waiting(snapshot: Any) -> bool:
        return any(task.interrupts for task in snapshot.tasks)

    def from_snapshot(self, run_id: str, *, version: int, history: list[str]) -> ReviewRecord:
        snapshot = self.snapshot(run_id)
        if not self.is_waiting(snapshot) or snapshot.values.get("run_id") != run_id:
            raise ReviewUnavailable("The pending review checkpoint is unavailable")
        return pending_review(
            snapshot.values, version=version, history=history, created_at=snapshot.created_at,
            revision_supported=self.runtime.provider.external,
        )

    def register(self, run_id: str) -> ReviewRecord:
        return self.reviews.add(self.from_snapshot(run_id, version=0, history=[]))

    def get(self, run_id: str) -> ReviewRecord | None:
        record = self.reviews.get(run_id)
        if record is None:
            return None
        if record.status == ReviewStatus.PENDING:
            return self.from_snapshot(
                run_id, version=record.version, history=record.feedback_history
            )
        update = {"can_approve": False, "can_revise": False}
        if record.status == ReviewStatus.ERROR:
            retry = self.decisions.unfinished(run_id)
            if retry and self._approval_block(record, retry):
                update.update(error=STALE_DRAFT, retry_decision=None)
            else:
                update["retry_decision"] = retry
        return record.model_copy(update=update)

    def _approval_block(self, record: ReviewRecord, decision: ReviewDecision) -> str | None:
        if decision.action != "approve" or record.status not in {
            ReviewStatus.PENDING, ReviewStatus.ERROR,
        }:
            return None
        if record.status == ReviewStatus.ERROR and self.runtime.memory.get_run(record.run_id):
            return None
        state = self.snapshot(record.run_id).values
        if state.get("run_id") == record.run_id and not has_current_validation(state):
            return STALE_DRAFT
        return None

    def list_open(self) -> list[ReviewRecord]:
        records = []
        for record in self.reviews.list_open():
            current = self.get(record.run_id)
            if current is None:
                raise ReviewUnavailable("A pending review disappeared during listing")
            records.append(current)
        return records

    def decide(
        self, run_id: str, decision: ReviewDecision
    ) -> ReviewRecord | AnalysisResult:
        existing = self.reviews.get(run_id)
        if existing is None:
            raise KeyError(run_id)
        cached = self.decisions.claim(
            run_id, decision, revision_supported=self.runtime.provider.external,
            approval_block=self._approval_block(existing, decision),
        )
        if cached is not None:
            value = json.loads(cached)
            return (
                ReviewRecord.model_validate(value)
                if "status" in value else AnalysisResult.model_validate(value)
            )
        try:
            if decision.action == "approve":
                saved = self.runtime.memory.get_run(run_id)
                if saved is not None:
                    return self._approved(existing, decision, saved)
            snapshot = self.snapshot(run_id)
            if self.is_waiting(snapshot):
                output = self.graph.invoke(
                    Command(resume=decision.model_dump(mode="json")), self.config(run_id)
                )
            elif snapshot.next:
                self.graph.update_state(
                    self.config(run_id), {"started_at": time.perf_counter()}
                )
                output = self.graph.invoke(None, self.config(run_id))
            else:
                if decision.action == "reject" and snapshot.values.get("run_id") == run_id:
                    return self._rejected(existing, decision)
                raise ReviewUnavailable("The review checkpoint cannot be resumed")
            if "__interrupt__" in output:
                if decision.action != "revise":
                    raise ReviewUnavailable("A final decision unexpectedly requested review")
                record = self.from_snapshot(
                    run_id,
                    version=existing.version + 1,
                    history=[*existing.feedback_history, decision.feedback or ""],
                )
                self.decisions.finish(decision, record, record)
                return record
            if "result" in output and decision.action == "approve":
                return self._approved(existing, decision, output["result"])
            if decision.action == "reject" and not self.snapshot(run_id).next:
                return self._rejected(existing, decision)
            raise ReviewUnavailable("The graph returned an unexpected review outcome")
        except Exception as exc:
            logger.exception("Review decision failed for %s", run_id)
            self.reviews.set_error(run_id, str(exc))
            raise

    def _approved(
        self, previous: ReviewRecord, decision: ReviewDecision, result: AnalysisResult
    ) -> AnalysisResult:
        record = previous.model_copy(update={
            "status": ReviewStatus.APPROVED,
            "version": previous.version + 1,
            "can_approve": False,
            "can_revise": False,
        })
        self.decisions.finish(decision, record, result)
        self.prune(previous.run_id)
        return result

    def _rejected(self, previous: ReviewRecord, decision: ReviewDecision) -> ReviewRecord:
        record = previous.model_copy(update={
            "status": ReviewStatus.REJECTED,
            "version": previous.version + 1,
            "can_approve": False,
            "can_revise": False,
            "feedback_history": [*previous.feedback_history, decision.feedback or ""],
        })
        self.decisions.finish(decision, record, record)
        self.prune(previous.run_id)
        return record

    def prune(self, run_id: str) -> None:
        try:
            self.graph.checkpointer.delete_thread(run_id)
        except (OSError, sqlite3.Error):
            logger.exception("Could not prune checkpoint for %s", run_id)
