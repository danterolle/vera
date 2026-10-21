import json
import logging
import sqlite3
import time
from typing import Any

from langgraph.types import Command

from vera.domain.reports import AnalysisResult
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.domain.state import GraphState
from vera.errors import ReviewUnavailable
from vera.memory.review_decisions import ReviewDecisions
from vera.memory.reviews import ReviewStore
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

    def from_snapshot(
        self, run_id: str, *, version: int, history: list[str]
    ) -> ReviewRecord:
        snapshot = self.snapshot(run_id)
        if not self.is_waiting(snapshot) or snapshot.values.get("run_id") != run_id:
            raise ReviewUnavailable("The pending review checkpoint is unavailable")
        state: GraphState = snapshot.values
        return ReviewRecord(
            run_id=run_id,
            status=ReviewStatus.PENDING,
            version=version,
            reasons=state["review_reasons"],
            query=state["request"].query,
            route=state["route"],
            draft=state["draft"],
            evidence=state["evidence"],
            incident=state["incident"],
            reflection=state["reflection"],
            warnings=state["warnings"],
            revision_count=state.get("revision_count", 0),
            can_revise=self.runtime.provider.external and state.get("revision_count", 0) < 2,
            feedback_history=history,
            error=state.get("revision_error"),
        )

    def register(self, run_id: str) -> ReviewRecord:
        return self.reviews.add(self.from_snapshot(run_id, version=0, history=[]))

    def get(self, run_id: str) -> ReviewRecord | None:
        record = self.reviews.get(run_id)
        if record:
            record = record.model_copy(
                update={
                    "can_revise": record.status == ReviewStatus.PENDING
                    and self.runtime.provider.external
                    and record.revision_count < 2
                }
            )
        if record and record.status == ReviewStatus.PENDING:
            self.from_snapshot(
                run_id, version=record.version, history=record.feedback_history
            )
        if record and record.status == ReviewStatus.ERROR:
            return record.model_copy(
                update={"retry_decision": self.decisions.unfinished(run_id)}
            )
        return record

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
            run_id, decision, revision_supported=self.runtime.provider.external
        )
        if cached is not None:
            value = json.loads(cached)
            return (
                ReviewRecord.model_validate(value)
                if "status" in value else AnalysisResult.model_validate(value)
            )
        try:
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
                saved = self.runtime.memory.get_run(run_id)
                if saved is not None and decision.action == "approve":
                    return self._approved(existing, decision, saved)
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
        record = previous.model_copy(
            update={
                "status": ReviewStatus.APPROVED,
                "version": previous.version + 1,
                "can_revise": False,
            }
        )
        self.decisions.finish(decision, record, result)
        self.prune(previous.run_id)
        return result

    def _rejected(
        self, previous: ReviewRecord, decision: ReviewDecision
    ) -> ReviewRecord:
        record = previous.model_copy(
            update={
                "status": ReviewStatus.REJECTED,
                "version": previous.version + 1,
                "can_revise": False,
                "feedback_history": [*previous.feedback_history, decision.feedback or ""],
            }
        )
        self.decisions.finish(decision, record, record)
        self.prune(previous.run_id)
        return record

    def prune(self, run_id: str) -> None:
        try:
            self.graph.checkpointer.delete_thread(run_id)
        except (OSError, sqlite3.Error):
            logger.exception("Could not prune checkpoint for %s", run_id)
