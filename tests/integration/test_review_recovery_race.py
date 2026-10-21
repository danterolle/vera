from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from vera.domain.enums import Route
from vera.domain.reports import GeneratedAnswer
from vera.domain.requests import AnalysisRequest
from vera.domain.review import ReviewRecord
from vera.workflow.orchestrator import VeraOrchestrator


class PausedProvider:
    name = "paused"
    external = True

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def classify(self, query):
        return Route.CAG_RAG

    def generate(self, request, route, evidence, alerts, statistics, feedback):
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise RuntimeError("The blocked model was not released")
        return GeneratedAnswer(summary="Incorrect scope.", out_of_scope=True)


def test_recovery_does_not_prune_another_orchestrators_active_thread(
    settings, monkeypatch
) -> None:
    run_id = uuid4()
    monkeypatch.setattr("vera.workflow.orchestrator.uuid4", lambda: run_id)
    provider = PausedProvider()
    active = VeraOrchestrator(settings, provider=provider)
    config = active.review_service.config(str(run_id))

    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(active.analyze, {"query": "Analyze CVE-2099-9999"})
        try:
            assert provider.entered.wait(timeout=10)
            assert active.checkpointer.get_tuple(config) is not None
            recovered = VeraOrchestrator(settings)
            assert active.checkpointer.get_tuple(config) is not None
        finally:
            provider.release.set()
        review = running.result(timeout=10)

    assert isinstance(review, ReviewRecord)
    stored = recovered.get_review(review.run_id)
    assert stored is not None
    assert stored.run_id == review.run_id
    assert stored.draft == review.draft
    assert active.checkpointer.get_tuple(config) is not None


def test_recovery_prunes_only_terminal_unregistered_saved_runs(settings) -> None:
    original = VeraOrchestrator(settings)
    run_id = str(uuid4())
    config = original.review_service.config(run_id)
    state = original.graph.invoke(
        {"request": AnalysisRequest(query="What is least privilege?"), "run_id": run_id},
        config,
    )
    assert state["result"].run_id == run_id
    assert original.checkpointer.get_tuple(config) is not None

    recovered = VeraOrchestrator(settings)
    assert recovered.get_run(run_id) == state["result"]
    assert recovered.checkpointer.get_tuple(config) is None


def test_recovery_registers_interrupt_before_original_writer(settings, monkeypatch) -> None:
    run_id = uuid4()
    monkeypatch.setattr("vera.workflow.orchestrator.uuid4", lambda: run_id)
    original = VeraOrchestrator(settings)
    entered = Event()
    release = Event()
    register = original.review_service.register

    def delayed_register(pending_id: str) -> ReviewRecord:
        entered.set()
        if not release.wait(timeout=10):
            raise RuntimeError("The pending review was not released")
        return register(pending_id)

    monkeypatch.setattr(original.review_service, "register", delayed_register)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(original.analyze, {"query": "Analyze CVE-2099-9999"})
        try:
            assert entered.wait(timeout=10)
            recovered = VeraOrchestrator(settings)
            pending = recovered.get_review(str(run_id))
            assert pending is not None
        finally:
            release.set()
        assert running.result(timeout=10) == pending

    assert original.checkpointer.get_tuple(original.review_service.config(str(run_id)))
