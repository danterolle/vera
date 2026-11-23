from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from vera.config import Settings
from vera.data import resource
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.errors import ReviewConflict
from vera.providers.deterministic import DeterministicProvider
from vera.reasoning.validation import VALIDATION_CONTRACT
from vera.stream.parsers import load_events
from vera.workflow.orchestrator import VeraOrchestrator


class StubModel(DeterministicProvider):
    name = "stub"
    external = True


class ReviewTests(TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.settings = Settings(
            _env_file=None,
            db_path=Path(directory) / "test.db",
            corpus_dir=Path(directory) / "corpus",
            live_sources=False,
            web_search_enabled=False,
            kg_enabled=False,
            react_enabled=False,
            llm_provider="deterministic",
            llm_model="original-model",
            embedding_backend="hash",
            memory_k=0,
        )
        self.request = AnalysisRequest(
            query="Analyze this controlled replay",
            events=load_events(
                Path(str(resource("samples/syn-flood.jsonl"))), self.settings.max_events
            ),
            simulated=True,
        )

    def pending(self, engine: VeraOrchestrator) -> ReviewRecord:
        record = engine.analyze(self.request)
        self.assertIsInstance(record, ReviewRecord)
        return record

    def test_resume_preserves_draft_metadata_and_decision_idempotency(self):
        with VeraOrchestrator(self.settings, provider=StubModel()) as engine:
            record = self.pending(engine)
            self.assertTrue(record.can_approve)
            self.assertIsNone(engine.get_run(record.run_id))

        settings = self.settings.model_copy(update={"llm_model": "replacement-model"})
        with VeraOrchestrator(settings, provider=StubModel()) as engine:
            resumed = engine.get_review(record.run_id)
            self.assertEqual(resumed.metadata["model"], "original-model")
            self.assertEqual(resumed.metadata["validation_contract"], VALIDATION_CONTRACT)
            approval = ReviewDecision(
                action="approve", version=resumed.version, decision_id=uuid4(),
            )
            result = engine.decide_review(record.run_id, approval)
            self.assertIsInstance(result, AnalysisResult)
            self.assertEqual(result.metadata["provider"], "stub")
            self.assertEqual(result.metadata["model"], "original-model")
            self.assertEqual(engine.decide_review(record.run_id, approval), result)
            self.assertEqual(len(engine.list_runs()), 1)

    def test_missing_contract_blocks_approval_but_allows_rejection(self):
        with (
            VeraOrchestrator(self.settings) as engine,
            patch("vera.workflow.nodes.VALIDATION_CONTRACT", None),
        ):
            record = self.pending(engine)

        with VeraOrchestrator(self.settings) as engine:
            resumed = engine.get_review(record.run_id)
            self.assertFalse(resumed.can_approve)
            self.assertIsNone(resumed.metadata["validation_contract"])
            approval = ReviewDecision(
                action="approve", version=resumed.version, decision_id=uuid4(),
            )
            with self.assertRaises(ReviewConflict):
                engine.decide_review(record.run_id, approval)
            self.assertIsNone(engine.get_run(record.run_id))
            rejection = ReviewDecision(
                action="reject", version=resumed.version, decision_id=uuid4(),
                feedback="Analyze again under the current contract.",
            )
            result = engine.decide_review(record.run_id, rejection)
            self.assertEqual(result.status, ReviewStatus.REJECTED)

    def test_interrupted_approval_can_retry_only_with_current_validation(self):
        for contract in (VALIDATION_CONTRACT, None):
            with self.subTest(contract=contract):
                with (
                    VeraOrchestrator(self.settings) as engine,
                    patch("vera.workflow.nodes.VALIDATION_CONTRACT", contract),
                ):
                    record = self.pending(engine)
                    decision = ReviewDecision(
                        action="approve", version=record.version, decision_id=uuid4(),
                    )
                    engine.review_service.decisions.claim(
                        record.run_id, decision, revision_supported=False, approval_block=None,
                    )

                with VeraOrchestrator(self.settings) as engine:
                    resumed = engine.get_review(record.run_id)
                    self.assertEqual(resumed.status, ReviewStatus.ERROR)
                    if contract is None:
                        self.assertIsNone(resumed.retry_decision)
                        with self.assertRaises(ReviewConflict):
                            engine.decide_review(record.run_id, decision)
                        self.assertIsNone(engine.get_run(record.run_id))
                    else:
                        self.assertEqual(resumed.retry_decision, decision)
                        result = engine.decide_review(record.run_id, decision)
                        self.assertIsInstance(result, AnalysisResult)

    def test_revision_revalidates_an_old_draft_and_requires_a_new_decision(self):
        with (
            VeraOrchestrator(self.settings, provider=StubModel()) as engine,
            patch("vera.workflow.nodes.VALIDATION_CONTRACT", "vera-evidence-v1"),
        ):
            record = self.pending(engine)

        settings = self.settings.model_copy(update={"llm_model": "revision-model"})
        with VeraOrchestrator(settings, provider=StubModel()) as engine:
            resumed = engine.get_review(record.run_id)
            self.assertFalse(resumed.can_approve)
            self.assertEqual(resumed.metadata["validation_contract"], "vera-evidence-v1")
            revision = ReviewDecision(
                action="revise", version=resumed.version, decision_id=uuid4(),
                feedback="Review the existing evidence again.",
            )
            revised = engine.decide_review(record.run_id, revision)
            self.assertEqual(revised.status, ReviewStatus.PENDING)
            self.assertEqual(revised.version, resumed.version + 1)
            self.assertTrue(revised.can_approve)
            self.assertEqual(revised.metadata["model"], "revision-model")
            self.assertEqual(revised.metadata["validation_contract"], VALIDATION_CONTRACT)
            self.assertIsNone(engine.get_run(record.run_id))
            with self.assertRaisesRegex(ReviewConflict, "review changed"):
                engine.decide_review(record.run_id, ReviewDecision(
                    action="approve", version=resumed.version, decision_id=uuid4(),
                ))

    def test_competing_approvals_publish_once(self):
        with VeraOrchestrator(self.settings) as engine:
            record = self.pending(engine)
            barrier = Barrier(2, timeout=5)

            def approve() -> AnalysisResult | None:
                decision = ReviewDecision(
                    action="approve", version=record.version, decision_id=uuid4(),
                )
                barrier.wait()
                try:
                    return engine.decide_review(record.run_id, decision)
                except ReviewConflict:
                    return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: approve(), range(2)))
            self.assertEqual(sum(result is not None for result in results), 1)
            saved = engine.get_run(record.run_id)
            self.assertIsNotNone(saved)
            self.assertTrue(saved.evidence)
            self.assertEqual(len(engine.list_runs()), 1)
