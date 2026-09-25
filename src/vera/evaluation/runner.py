import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel, Field

from vera.config import Settings
from vera.data import resource
from vera.domain.enums import EvidenceStatus, Route, SourceType
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


class EvaluationReport(BaseModel):
    passed: bool
    routing_accuracy: float
    retrieval_success_rate: float
    average_source_coverage: float
    average_latency_ms: float
    total_model_calls: int
    total_tool_calls: int
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
    return EvaluationReport(
        passed=all(item.passed for item in results),
        routing_accuracy=sum(
            item.actual_route == item.expected_route for item in results
        )
        / count,
        retrieval_success_rate=sum(item.passed for item in results) / count,
        average_source_coverage=sum(item.source_coverage for item in results) / count,
        average_latency_ms=sum(item.latency_ms for item in results) / count,
        total_model_calls=sum(item.model_calls for item in results),
        total_tool_calls=sum(item.tool_calls for item in results),
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
    passed = (
        result.route == scenario.expected_route
        and available >= scenario.minimum_available_sources
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
    )


def _load_scenarios() -> list[EvaluationScenario]:
    payload = json.loads(resource("evaluation/scenarios.json").read_text())
    return [EvaluationScenario.model_validate(item) for item in payload]
