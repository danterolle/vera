import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel, Field

from vera.config import Settings
from vera.data import resource
from vera.domain.enums import ClaimStatus, EvidenceStatus, Route, SourceType
from vera.domain.requests import AnalysisRequest
from vera.stream.parsers import load_events
from vera.workflow.orchestrator import VeraOrchestrator


class EvaluationScenario(BaseModel):
    name: str
    query: str
    expected_route: Route
    minimum_available_sources: int = Field(ge=0)
    events_file: str | None = None
    simulated: bool = False
    expected_rules: list[str] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    name: str
    passed: bool
    expected_route: Route
    actual_route: Route
    available_sources: int
    source_coverage: float
    latency_ms: float
    model_calls: int
    tool_calls: int
    detector_match: bool
    expected_rules: list[str]
    actual_rules: list[str]
    grounded_claims: int
    factual_claims: int
    unsupported_claims: int
    validation_failures: int
    factual_validation_failures: int
    retrieval_match: bool
    has_events: bool


class EvaluationReport(BaseModel):
    passed: bool
    routing_accuracy: float
    retrieval_success_rate: float
    average_source_coverage: float
    average_latency_ms: float
    total_model_calls: int
    total_tool_calls: int
    detector_accuracy: float
    grounding_rate: float
    unsupported_claims: int
    scenarios: list[ScenarioResult]


def run_evaluation(settings: Settings | None = None) -> EvaluationReport:
    configured = settings or Settings()
    scenarios = _load_scenarios()
    with TemporaryDirectory(prefix="vera-evaluation-") as directory:
        isolated = configured.model_copy(
            update={
                "db_path": Path(directory) / "evaluation.db",
                "corpus_dir": Path(directory) / "corpus",
                "live_sources": False,
            }
        )
        orchestrator = VeraOrchestrator(isolated)
        results = [_run_scenario(orchestrator, scenario) for scenario in scenarios]
    count = len(results)
    event_results = [item for item in results if item.has_events]
    factual_claims = sum(item.factual_claims for item in results)
    factual_failures = sum(item.factual_validation_failures for item in results)
    return EvaluationReport(
        passed=all(item.passed for item in results),
        routing_accuracy=sum(
            item.actual_route == item.expected_route for item in results
        )
        / count,
        retrieval_success_rate=sum(item.retrieval_match for item in results) / count,
        average_source_coverage=sum(item.source_coverage for item in results) / count,
        average_latency_ms=sum(item.latency_ms for item in results) / count,
        total_model_calls=sum(item.model_calls for item in results),
        total_tool_calls=sum(item.tool_calls for item in results),
        detector_accuracy=(
            sum(item.detector_match for item in event_results) / len(event_results)
            if event_results
            else 1.0
        ),
        grounding_rate=(
            sum(item.grounded_claims for item in results)
            / (factual_claims + factual_failures)
            if factual_claims + factual_failures
            else 1.0
        ),
        unsupported_claims=sum(item.unsupported_claims for item in results),
        scenarios=results,
    )


def _run_scenario(
    orchestrator: VeraOrchestrator,
    scenario: EvaluationScenario,
) -> ScenarioResult:
    events = []
    if scenario.events_file:
        path = Path(str(resource(f"samples/{scenario.events_file}")))
        events = load_events(path, orchestrator.settings.max_events)
    result = orchestrator.analyze(
        AnalysisRequest(
            query=scenario.query,
            events=events,
            simulated=scenario.simulated,
        )
    )
    available = len(
        {
            item.source
            for item in result.evidence
            if item.status == EvidenceStatus.AVAILABLE and item.source != SourceType.MEMORY
        }
    )
    actual_rules = sorted(
        alert.rule_id for alert in result.incident.alerts
    ) if result.incident else []
    expected_rules = sorted(scenario.expected_rules)
    detector_match = actual_rules == expected_rules
    retrieval_match = available >= scenario.minimum_available_sources
    factual = [
        claim for claim in result.claims if claim.status == ClaimStatus.SUPPORTED_FACT
    ]
    passed = (
        result.route == scenario.expected_route
        and retrieval_match
        and detector_match
        and result.reflection.validation_failures == 0
    )
    return ScenarioResult(
        name=scenario.name,
        passed=passed,
        expected_route=scenario.expected_route,
        actual_route=result.route,
        available_sources=available,
        source_coverage=result.metrics.source_coverage,
        latency_ms=result.metrics.latency_ms,
        model_calls=result.metrics.model_calls,
        tool_calls=result.metrics.tool_calls,
        detector_match=detector_match,
        expected_rules=expected_rules,
        actual_rules=actual_rules,
        grounded_claims=sum(bool(claim.citations) for claim in factual),
        factual_claims=len(factual),
        unsupported_claims=result.reflection.unsupported_claims,
        validation_failures=result.reflection.validation_failures,
        factual_validation_failures=result.reflection.factual_validation_failures,
        retrieval_match=retrieval_match,
        has_events=bool(events),
    )


def _load_scenarios() -> list[EvaluationScenario]:
    payload = json.loads(resource("evaluation/scenarios.json").read_text())
    return [EvaluationScenario.model_validate(item) for item in payload]
