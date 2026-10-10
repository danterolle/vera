from datetime import UTC, datetime, timedelta
from pathlib import Path

from vera.data import resource
from vera.domain.enums import ClaimStatus, Route, SourceType
from vera.domain.requests import AnalysisRequest, NetworkEvent
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


def test_uncovered_concept_uses_retrieval(settings) -> None:
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="How does zero trust work?")
    )
    assert result.route == Route.CAG_RAG
    assert any("Zero Trust Architecture" in item.title for item in result.evidence)
    cited_titles = {
        item.title
        for claim in result.claims
        for item in result.evidence
        if item.id in claim.evidence_ids
    }
    assert "NIST SP 800-207 - Zero Trust Architecture" in cited_titles


def test_uncovered_concept_with_events_keeps_retrieval(settings) -> None:
    events = load_events(Path(str(resource("samples/benign-web.jsonl"))))
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(
            query="How does zero trust relate to this traffic?",
            events=events,
            simulated=True,
        )
    )
    assert result.route == Route.FULL
    assert result.metadata["resource_plan"]["use_stream"]
    assert result.metadata["resource_plan"]["use_rag"]


def test_requested_evidence_policy_is_not_treated_as_fallback(settings) -> None:
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Explain evidence and inference policy.")
    )
    assert result.claims[0].status == ClaimStatus.SUPPORTED_FACT
    cited = {
        item.title
        for item in result.evidence
        if item.id in result.claims[0].evidence_ids
    }
    assert cited == {"Evidence and inference policy"}


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


def test_mixed_cve_and_benign_stream_acquires_both_contexts(settings) -> None:
    path = Path(str(resource("samples/benign-web.jsonl")))
    events = load_events(path)
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(
            query="Analyze CVE-2021-44228 in this traffic.",
            events=events,
            simulated=True,
        )
    )
    plan = result.metadata["resource_plan"]
    assert result.route == Route.FULL
    assert plan["use_stream"]
    assert plan["use_rag"]
    assert plan["use_tools"]
    assert SourceType.STREAM in {item.source for item in result.evidence}
    assert SourceType.CVE_ORG in {item.source for item in result.evidence}


def test_deterministic_stream_report_is_human_readable(settings) -> None:
    path = Path(str(resource("samples/benign-web.jsonl")))
    events = load_events(path)
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Analyze benign traffic.", events=events, simulated=True)
    )
    assert "No deterministic detection rule fired" in result.answer
    assert '{"alerts"' not in result.answer
    assert "Observed protocols:" in result.answer


def test_event_level_simulation_flag_is_preserved(settings) -> None:
    path = Path(str(resource("samples/benign-web.jsonl")))
    events = load_events(path)
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Analyze traffic.", events=events)
    )
    assert result.claims[0].status == ClaimStatus.SIMULATED


def test_offline_cve_report_omits_unrelated_retrieval_claims(settings) -> None:
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Analyze CVE-2021-44228.")
    )
    supported_titles = {
        item.title
        for claim in result.claims
        if claim.status == ClaimStatus.SUPPORTED_FACT
        for item in result.evidence
        if item.id in claim.evidence_ids
    }
    assert supported_titles == {"CVE-2021-44228 - NVD snapshot"}
    assert len([claim for claim in result.claims if claim.status == ClaimStatus.UNAVAILABLE]) == 1
    assert "without current live data" in result.answer


def test_large_alert_batch_is_summarized_safely(settings) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        NetworkEvent(
            timestamp=start + timedelta(milliseconds=index),
            src_ip="198.51.100.8",
            dst_ip="10.0.0.8",
            src_port=50000 + index,
            dst_port=8080,
            protocol="HTTP",
            http_method="GET",
            http_uri=f"/files/{index}/../secret",
            http_status=400,
            simulated=True,
        )
        for index in range(35)
    ]
    result = VeraOrchestrator(settings).analyze(
        AnalysisRequest(query="Analyze this traffic.", events=events, simulated=True)
    )
    stream = next(item for item in result.evidence if item.source == SourceType.STREAM)
    assert result.incident is not None
    assert len(result.incident.alerts) == 35
    assert len(stream.content) < 12_000
    assert stream.metadata["rule_counts"] == {"HTTP-PATH-TRAVERSAL": 35}
    simulated_claims = [
        claim for claim in result.claims if claim.status == ClaimStatus.SIMULATED
    ]
    assert len(simulated_claims) == 1
