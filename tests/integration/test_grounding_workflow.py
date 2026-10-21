from pathlib import Path

from vera.data import resource
from vera.domain.enums import ClaimStatus, Route, SourceType
from vera.domain.evidence import Citation, Claim
from vera.domain.reports import GeneratedAnswer
from vera.domain.requests import AnalysisRequest
from vera.stream.parsers import load_events
from vera.workflow.orchestrator import VeraOrchestrator


class UngroundedProvider:
    name = "ungrounded"
    external = False

    def classify(self, query: str) -> Route:
        return Route.CAG_ONLY

    def generate(self, request, route, evidence, alerts, statistics, feedback):
        item = evidence[0]
        return GeneratedAnswer(
            summary="Invalid grounding test",
            claims=[
                Claim(
                    text="The Moon is made of cheese.",
                    status=ClaimStatus.SUPPORTED_FACT,
                    evidence_ids=[item.id],
                    citations=[
                        Citation(
                            evidence_id=item.id,
                            supporting_quote=item.content,
                        )
                    ],
                )
            ],
        )


class SimulatedFactProvider:
    name = "simulated-fact"
    external = False

    def classify(self, query: str) -> Route:
        return Route.STREAM

    def generate(self, request, route, evidence, alerts, statistics, feedback):
        item = next(value for value in evidence if value.source == SourceType.STREAM)
        return GeneratedAnswer(
            summary="Invalid simulated fact",
            claims=[
                Claim(
                    text=item.content,
                    status=ClaimStatus.SUPPORTED_FACT,
                    evidence_ids=[item.id],
                    citations=[
                        Citation(
                            evidence_id=item.id,
                            supporting_quote=item.content,
                        )
                    ],
                )
            ],
        )


def test_ungrounded_provider_claim_reduces_quality_metrics(settings) -> None:
    result = VeraOrchestrator(
        settings, provider=UngroundedProvider(), review_enabled=False
    ).analyze(
        AnalysisRequest(query="What is defense in depth?")
    )
    assert result.claims[0].status == ClaimStatus.SYSTEM_INFERENCE
    assert result.reflection.completeness_score == 0.0
    assert result.reflection.unsupported_claims == 1
    assert result.reflection.validation_failures == 1
    assert result.reflection.grounding_failures == 1
    assert result.metrics.source_coverage == 0.0


def test_simulated_fact_downgrade_is_counted_as_grounding_failure(settings) -> None:
    events = load_events(Path(str(resource("samples/benign-web.jsonl"))))
    result = VeraOrchestrator(
        settings, provider=SimulatedFactProvider(), review_enabled=False
    ).analyze(
        AnalysisRequest(query="Analyze traffic.", events=events, simulated=True)
    )
    assert result.claims[0].status == ClaimStatus.SIMULATED
    assert result.reflection.completeness_score == 0.0
    assert result.reflection.grounding_failures == 1
    assert result.reflection.unsupported_claims == 1
    assert result.metrics.source_coverage == 0.0
