from pathlib import Path

from vera.data import resource
from vera.domain.enums import ClaimStatus, Route, SourceType
from vera.domain.requests import AnalysisRequest
from vera.stream.parsers import load_events
from vera.workflow.orchestrator import VeraOrchestrator


def test_conceptual_workflow_is_persisted(settings) -> None:
    orchestrator = VeraOrchestrator(settings)
    result = orchestrator.analyze(AnalysisRequest(query="What is defense in depth?"))
    assert result.route == Route.CAG_ONLY
    assert result.metrics.model_calls == 0
    assert result.metrics.tool_calls == 0
    assert result.reflection.completeness_score == 1.0
    assert orchestrator.get_run(result.run_id) == result


def test_cve_workflow_marks_disabled_sources(settings) -> None:
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Analyze CVE-2021-44228")
    )
    assert result.route == Route.CAG_RAG_TOOL
    assert result.metrics.tool_calls == 0
    assert result.warnings
    assert any(claim.status == ClaimStatus.UNAVAILABLE for claim in result.claims)
    assert any(claim.status == ClaimStatus.SUPPORTED_FACT for claim in result.claims)
    cve_record = next(item for item in result.evidence if item.source == SourceType.CVE_ORG)
    assert any(cve_record.id in claim.evidence_ids for claim in result.claims)


def test_simulated_stream_runs_full_pipeline(settings) -> None:
    path = Path(str(resource("samples/network-events.jsonl")))
    events = load_events(path)
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Analyze this replay", events=events, simulated=True)
    )
    assert result.route == Route.FULL
    assert result.incident is not None
    assert result.incident.alerts
    assert any(claim.status == ClaimStatus.SIMULATED for claim in result.claims)
