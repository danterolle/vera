from vera.config import Settings
from vera.domain.enums import ClaimStatus, Route
from vera.domain.evidence import Citation, Claim
from vera.domain.reports import GeneratedAnswer
from vera.domain.requests import AnalysisRequest
from vera.errors import ProviderError
from vera.workflow.orchestrator import VeraOrchestrator


class RetryProvider:
    name = "retry"
    external = True

    def __init__(self) -> None:
        self.classify_calls = 0
        self.generation_calls = 0

    def classify(self, query: str) -> Route:
        self.classify_calls += 1
        return Route.CAG_ONLY

    def generate(self, request, route, evidence, alerts, statistics, feedback):
        self.generation_calls += 1
        evidence_id = "ev-missing" if self.generation_calls == 1 else evidence[0].id
        quote = "missing quote" if self.generation_calls == 1 else evidence[0].content
        claim_text = "Unsupported claim" if self.generation_calls == 1 else quote
        return GeneratedAnswer(
            summary="Generated",
            claims=[
                Claim(
                    text=claim_text,
                    status=ClaimStatus.SUPPORTED_FACT,
                    evidence_ids=[evidence_id],
                    citations=[
                        Citation(
                            evidence_id=evidence_id,
                            supporting_quote=quote,
                        )
                    ],
                )
            ],
        )


def test_invalid_generation_uses_one_bounded_retry(tmp_path) -> None:
    provider = RetryProvider()
    settings = Settings(
        db_path=tmp_path / "retry.db",
        live_sources=False,
        max_model_calls=2,
    )
    result = VeraOrchestrator(settings, provider=provider).analyze(
        AnalysisRequest(query="What is defense in depth?")
    )
    assert provider.generation_calls == 2
    assert result.metrics.model_calls == 2
    assert result.claims[0].status == ClaimStatus.SUPPORTED_FACT


def test_routing_call_consumes_global_model_budget(tmp_path) -> None:
    provider = RetryProvider()
    settings = Settings(
        db_path=tmp_path / "budget.db",
        live_sources=False,
        max_model_calls=1,
    )
    result = VeraOrchestrator(settings, provider=provider).analyze(
        AnalysisRequest(query="Assess this unusual security situation")
    )
    assert provider.classify_calls == 1
    assert provider.generation_calls == 0
    assert result.metrics.model_calls == 1
    assert any("model-call limit" in warning for warning in result.warnings)


def test_provider_failure_is_visible_in_saved_result(settings) -> None:
    class FailedProvider(RetryProvider):
        def generate(self, *args, **kwargs):
            raise ProviderError("Local model is unavailable")

    result = VeraOrchestrator(settings, provider=FailedProvider()).analyze(
        AnalysisRequest(query="What is defense in depth?")
    )
    assert result.metadata["provider_fallback"] is True
    assert any("Local model is unavailable" in warning for warning in result.warnings)
