import pytest

from vera.domain.enums import Route
from vera.providers.deterministic import DeterministicProvider
from vera.routing.router import Router


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is defense in depth?", Route.CAG_ONLY),
        ("Explain MITRE ATT&CK T1190", Route.CAG_RAG),
        ("Analyze CVE-2021-44228", Route.CAG_RAG_TOOL),
        ("Show the latest vulnerability context", Route.CAG_RAG),
        ("Assess this unusual security situation", Route.CAG_RAG),
    ],
)
def test_text_routes(query: str, expected: Route) -> None:
    decision = Router(DeterministicProvider()).select(query, False, False)
    assert decision.route == expected


def test_event_routes() -> None:
    router = Router(DeterministicProvider())
    assert router.select("Analyze", True, False).route == Route.STREAM
    assert router.select("Analyze", True, True).route == Route.FULL
