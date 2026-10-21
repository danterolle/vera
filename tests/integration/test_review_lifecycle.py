from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from langgraph.types import Command

from vera.domain.enums import ClaimStatus, EvidenceStatus, Route
from vera.domain.evidence import Citation, Claim
from vera.domain.reports import AnalysisResult, GeneratedAnswer
from vera.domain.requests import AnalysisRequest
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.errors import ProviderError, ReviewConflict, ReviewUnavailable
from vera.workflow.orchestrator import VeraOrchestrator


def decide(record: ReviewRecord, action: str, feedback: str | None = None) -> ReviewDecision:
    return ReviewDecision(
        action=action, version=record.version, decision_id=uuid4(), feedback=feedback
    )


class ScopeProvider:
    name = "scope-test"
    external = True

    def classify(self, query):
        return Route.CAG_RAG

    def generate(self, request, route, evidence, alerts, statistics, feedback):
        if not feedback:
            return GeneratedAnswer(summary="Unrelated request.", out_of_scope=True)
        item = next(
            item for item in evidence
            if "CVE-2021-44228" in item.title and item.status == EvidenceStatus.AVAILABLE
        )
        quote = item.content[:100]
        return GeneratedAnswer(
            summary="Revised from cited evidence.",
            claims=[
                Claim(
                    text=quote,
                    status=ClaimStatus.SUPPORTED_FACT,
                    evidence_ids=[item.id],
                    citations=[Citation(evidence_id=item.id, supporting_quote=quote)],
                )
            ],
        )


class FailedRevisionProvider(ScopeProvider):
    def generate(self, request, route, evidence, alerts, statistics, feedback):
        if feedback:
            raise ProviderError("Local model is unavailable")
        return super().generate(request, route, evidence, alerts, statistics, feedback)


def test_unknown_cve_survives_restart_until_approval(settings) -> None:
    engine = VeraOrchestrator(settings)
    review = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(review, ReviewRecord)
    assert review.status == ReviewStatus.PENDING
    assert any("CVE-2099-9999" in reason for reason in review.reasons)
    assert engine.get_run(review.run_id) is None
    assert engine.list_runs() == []

    restored = VeraOrchestrator(settings)
    assert restored.get_review(review.run_id) == review
    choice = decide(review, "approve")
    report = restored.decide_review(review.run_id, choice)
    assert isinstance(report, AnalysisResult)
    assert report.run_id == review.run_id
    assert report.metadata["human_review"]["decision"] == "approved"
    assert restored.get_run(report.run_id) == report
    assert restored.decide_review(review.run_id, choice) == report
    with pytest.raises(ReviewConflict):
        restored.decide_review(review.run_id, decide(review, "reject", "Not reliable"))


def test_false_scope_decision_is_revised_twice_and_requires_approval(settings) -> None:
    engine = VeraOrchestrator(settings, provider=ScopeProvider())
    review = engine.analyze({"query": "Analyze CVE-2021-44228"})
    assert isinstance(review, ReviewRecord)
    assert review.draft.out_of_scope
    assert any("out of scope" in reason for reason in review.reasons)

    for round_number in (1, 2):
        feedback = f"This is a cybersecurity CVE; revise round {round_number}."
        review = engine.decide_review(review.run_id, decide(review, "revise", feedback))
        assert isinstance(review, ReviewRecord)
        assert review.status == ReviewStatus.PENDING
        assert review.revision_count == round_number
        assert review.feedback_history[-1] == feedback
        assert not review.draft.out_of_scope
        assert review.reflection.unsupported_claims == 0
        assert engine.get_run(review.run_id) is None
    with pytest.raises(ReviewConflict, match="two revision cycles"):
        engine.decide_review(review.run_id, decide(review, "revise", "Try again"))
    report = engine.decide_review(review.run_id, decide(review, "approve"))
    assert isinstance(report, AnalysisResult)
    assert report.metrics.model_calls == 3
    assert report.metadata["human_review"]["revision_count"] == 2


def test_revision_model_failure_keeps_unpublished_draft(settings) -> None:
    engine = VeraOrchestrator(settings, provider=FailedRevisionProvider())
    original = engine.analyze({"query": "Analyze CVE-2021-44228"})
    assert isinstance(original, ReviewRecord)
    pending = engine.decide_review(original.run_id, decide(original, "revise", "Correct scope"))
    assert isinstance(pending, ReviewRecord)
    assert pending.status == ReviewStatus.PENDING
    assert pending.error == "Local model is unavailable"
    assert pending.draft == original.draft
    assert engine.get_run(original.run_id) is None
    rejected = engine.decide_review(pending.run_id, decide(pending, "reject", "No reliable answer"))
    assert rejected.status == ReviewStatus.REJECTED
    assert engine.get_run(original.run_id) is None
    assert engine.list_reviews() == []


def test_orphan_checkpoint_is_reindexed_and_missing_one_fails_closed(settings) -> None:
    engine = VeraOrchestrator(settings)
    run_id = str(uuid4())
    state = engine.graph.invoke(
        {"request": AnalysisRequest(query="Analyze CVE-2099-9999"), "run_id": run_id},
        engine.review_service.config(run_id),
    )
    assert "__interrupt__" in state
    recovered = VeraOrchestrator(settings)
    review = recovered.get_review(run_id)
    assert review is not None
    recovered.checkpointer.delete_thread(run_id)
    with pytest.raises(ReviewUnavailable, match="checkpoint"):
        recovered.get_review(run_id)


def test_approval_committed_before_ledger_update_recovers(settings) -> None:
    engine = VeraOrchestrator(settings)
    review = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(review, ReviewRecord)
    choice = decide(review, "approve")
    engine.review_service.decisions.claim(review.run_id, choice)
    outcome = engine.graph.invoke(
        Command(resume=choice.model_dump(mode="json")),
        engine.review_service.config(review.run_id),
    )
    assert "result" in outcome
    recovered = VeraOrchestrator(settings)
    assert recovered.get_review(review.run_id).status == ReviewStatus.APPROVED
    assert recovered.decide_review(review.run_id, choice) == outcome["result"]


def test_interrupted_decision_can_be_retried_after_restart(settings) -> None:
    engine = VeraOrchestrator(settings)
    review = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(review, ReviewRecord)
    choice = decide(review, "approve")
    engine.review_service.decisions.claim(review.run_id, choice)
    recovered = VeraOrchestrator(settings)
    errored = recovered.get_review(review.run_id)
    assert errored.status == ReviewStatus.ERROR
    assert errored.retry_decision == choice
    report = recovered.decide_review(review.run_id, errored.retry_decision)
    assert isinstance(report, AnalysisResult)
    assert recovered.get_review(review.run_id).status == ReviewStatus.APPROVED


def test_revision_checkpoint_is_reconciled_after_restart(settings) -> None:
    engine = VeraOrchestrator(settings, provider=ScopeProvider())
    review = engine.analyze({"query": "Analyze CVE-2021-44228"})
    assert isinstance(review, ReviewRecord)
    choice = decide(review, "revise", "Recognize the cybersecurity identifier")
    engine.review_service.decisions.claim(review.run_id, choice)
    resumed = engine.graph.invoke(
        Command(resume=choice.model_dump(mode="json")),
        engine.review_service.config(review.run_id),
    )
    assert "__interrupt__" in resumed
    recovered = VeraOrchestrator(settings, provider=ScopeProvider())
    pending = recovered.get_review(review.run_id)
    assert pending.version == 1
    assert pending.revision_count == 1
    assert recovered.decide_review(review.run_id, choice) == pending


def test_competing_review_decisions_publish_only_once(settings) -> None:
    engine = VeraOrchestrator(settings)
    review = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(review, ReviewRecord)
    decisions = [decide(review, "approve"), decide(review, "reject", "Insufficient evidence")]

    def submit(choice):
        try:
            return engine.decide_review(review.run_id, choice)
        except ReviewConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, decisions))
    assert sum(isinstance(item, ReviewConflict) for item in outcomes) == 1
    assert sum(isinstance(item, (AnalysisResult, ReviewRecord)) for item in outcomes) == 1
