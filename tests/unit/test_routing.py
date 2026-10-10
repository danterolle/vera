import pytest

from vera.domain.enums import Route, Severity
from vera.domain.reports import DetectionAlert
from vera.providers.deterministic import DeterministicProvider
from vera.routing.router import Router


class InvalidEventRouteProvider:
    name = "invalid-route"
    external = True

    def classify(self, query: str) -> Route:
        return Route.FULL


class UnsupportedCagProvider:
    name = "unsupported-cag"
    external = True

    def classify(self, query: str) -> Route:
        return Route.CAG_ONLY


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is defense in depth?", Route.CAG_ONLY),
        ("Explain MITRE ATT&CK T1190", Route.CAG_RAG),
        ("Analyze CVE-2021-44228", Route.CAG_RAG_TOOL),
        ("Show the latest vulnerability context", Route.CAG_RAG),
        ("Assess this unusual security situation", Route.CAG_RAG),
        ("How does zero trust work?", Route.CAG_RAG),
        ("Why is defense in depth useful?", Route.CAG_ONLY),
        ("Can you explain least privilege?", Route.CAG_ONLY),
        ("Che cos'e una CVE?", Route.CAG_ONLY),
        ("What is defense evasion?", Route.CAG_RAG),
        ("What is risk?", Route.CAG_RAG),
    ],
)
def test_text_routes(query: str, expected: Route) -> None:
    decision = Router(DeterministicProvider()).select(query, False, [])
    assert decision.route == expected


def test_event_routes() -> None:
    router = Router(DeterministicProvider())
    assert router.select("Analyze", True, []).route == Route.STREAM
    alert = DetectionAlert(
        rule_id="TEST",
        title="Test",
        description="Test alert",
        severity=Severity.MEDIUM,
    )
    assert router.select("Analyze", True, [alert]).route == Route.FULL


def test_mixed_cve_and_stream_plan_uses_all_resources() -> None:
    decision = Router(DeterministicProvider()).select(
        "Analyze CVE-2021-44228 in this traffic.",
        True,
        [],
    )
    assert decision.route == Route.FULL
    assert decision.plan.use_stream
    assert decision.plan.use_rag
    assert decision.plan.use_tools
    assert decision.plan.cve_ids == ["CVE-2021-44228"]


def test_event_only_llm_route_uses_safe_fallback_without_events() -> None:
    decision = Router(InvalidEventRouteProvider()).select(
        "Assess an unusual security situation.",
        False,
        [],
    )
    assert decision.route == Route.CAG_RAG
    assert decision.model_calls == 1
    assert decision.warnings


def test_llm_cag_route_requires_curated_coverage() -> None:
    decision = Router(UnsupportedCagProvider(), lambda query: False).select(
        "Discuss an unusual concept.",
        False,
        [],
    )
    assert decision.route == Route.CAG_RAG
