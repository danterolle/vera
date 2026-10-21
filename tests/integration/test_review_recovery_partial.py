import time
from uuid import uuid4

import pytest
from langgraph.types import Command

from vera.domain.enums import ClaimStatus, Route
from vera.domain.evidence import Claim
from vera.domain.reports import AnalysisResult, GeneratedAnswer
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.workflow.orchestrator import VeraOrchestrator


class InterruptedRevisionProvider:
    name = "interrupted-revision"
    external = True

    def __init__(self, *, fail: bool) -> None:
        self.fail = fail

    def classify(self, query):
        return Route.CAG_RAG

    def generate(self, request, route, evidence, alerts, statistics, feedback):
        if not feedback:
            return GeneratedAnswer(summary="Incorrect scope.", out_of_scope=True)
        if self.fail:
            raise RuntimeError("The process stopped during model generation")
        return GeneratedAnswer(
            summary="Missing current evidence.",
            claims=[Claim(text="Current data unavailable.", status=ClaimStatus.UNAVAILABLE)],
        )


def test_interrupted_revision_resumes_without_counting_human_wait(settings) -> None:
    provider = InterruptedRevisionProvider(fail=True)
    engine = VeraOrchestrator(settings, provider=provider)
    pending = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)
    choice = ReviewDecision(
        action="revise",
        version=pending.version,
        decision_id=uuid4(),
        feedback="This is a cybersecurity CVE.",
    )
    engine.review_service.decisions.claim(pending.run_id, choice)
    original_active = engine.review_service.snapshot(pending.run_id).values["active_ms"]
    with pytest.raises(RuntimeError, match="process stopped"):
        engine.graph.invoke(
            Command(resume=choice.model_dump(mode="json")),
            engine.review_service.config(pending.run_id),
        )
    recovered = VeraOrchestrator(
        settings, provider=InterruptedRevisionProvider(fail=False)
    )
    errored = recovered.get_review(pending.run_id)
    assert errored.status == ReviewStatus.ERROR
    assert errored.retry_decision == choice
    time.sleep(0.3)
    revised = recovered.decide_review(pending.run_id, choice)
    assert revised.status == ReviewStatus.PENDING
    assert revised.revision_count == 1
    active = recovered.review_service.snapshot(pending.run_id).values["active_ms"]
    assert active - original_active < 250

    pause_started = time.perf_counter()
    time.sleep(0.5)
    approved = recovered.decide_review(
        pending.run_id,
        ReviewDecision(action="approve", version=revised.version, decision_id=uuid4()),
    )
    assert isinstance(approved, AnalysisResult)
    elapsed_ms = (time.perf_counter() - pause_started) * 1000
    assert approved.metrics.latency_ms - active < elapsed_ms - 250


def test_unexpected_revision_error_is_retryable_without_server_restart(settings) -> None:
    provider = InterruptedRevisionProvider(fail=True)
    engine = VeraOrchestrator(settings, provider=provider)
    pending = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)
    decision = ReviewDecision(
        action="revise",
        version=pending.version,
        decision_id=uuid4(),
        feedback="This is a cybersecurity CVE.",
    )

    with pytest.raises(RuntimeError, match="process stopped"):
        engine.decide_review(pending.run_id, decision)
    failed = engine.get_review(pending.run_id)
    assert failed.status == ReviewStatus.ERROR
    assert failed.retry_decision == decision
    assert engine.get_run(pending.run_id) is None

    provider.fail = False
    revised = engine.decide_review(pending.run_id, failed.retry_decision)
    assert revised.status == ReviewStatus.PENDING
    assert revised.revision_count == 1
    assert engine.decide_review(pending.run_id, decision) == revised
