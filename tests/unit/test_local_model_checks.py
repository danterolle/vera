import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import httpx
import pytest

from vera.domain.enums import Route
from vera.domain.reports import GeneratedAnswer, ReflectionReport
from vera.domain.review import ReviewRecord, ReviewStatus

SCRIPT = run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/check-local-model.py"),
    run_name="local_model_checks",
)
CHECK = SCRIPT["check"]
SUMMARIZE = SCRIPT["summarize"]
MAIN = SCRIPT["main"]


def result(*, out_of_scope: bool, assessment: str, claims: list[dict] | None = None) -> dict:
    return {
        "metadata": {"model": "test-model", "provider_fallback": False,
                     "out_of_scope": out_of_scope,
                     "knowledge_graph": {"cited_evidence_ids": []}},
        "answer": f"## Assessment\n{assessment}\n\n## Sources\n"
                  "- No evidence was cited in the final claims.",
        "claims": claims or [],
    }


def test_missing_case_rejects_out_of_scope_refusal() -> None:
    refusal = result(
        out_of_scope=True, assessment="VERA answers only cybersecurity questions."
    )
    assert not CHECK(refusal, "missing", "test-model")
    assert CHECK(refusal, "scope", "test-model")


def test_missing_case_checks_assessment_not_source_footer() -> None:
    unrelated = result(out_of_scope=False, assessment="I cannot determine the CVE status.")
    assert not CHECK(unrelated, "missing", "test-model")
    assert CHECK(
        result(out_of_scope=False, assessment="Evidence for this CVE is unavailable."),
        "missing",
        "test-model",
    )


def test_missing_case_rejects_fabricated_supported_fact() -> None:
    unsupported = result(
        out_of_scope=False,
        assessment="Evidence for this CVE is missing.",
        claims=[{"status": "supported_fact"}],
    )
    assert not CHECK(unsupported, "missing", "test-model")
    assert not CHECK(
        result(out_of_scope=False, assessment="VERA answers only cybersecurity questions."),
        "scope",
        "test-model",
    )


def test_graph_case_requires_in_scope_cited_evidence() -> None:
    report = result(
        out_of_scope=True,
        assessment="PowerShell is a scripting interpreter.",
        claims=[{"status": "supported_fact"}],
    )
    report["metadata"]["knowledge_graph"] = {
        "attempted": True, "available": True, "cited_evidence_ids": ["ev-12345678"]
    }
    report["reflection"] = {"factual_validation_failures": 0}
    assert not CHECK(report, "graph", "test-model")
    report["metadata"]["out_of_scope"] = False
    assert CHECK(report, "graph", "test-model")


def pending_review() -> dict:
    return ReviewRecord(
        run_id="review-123",
        status=ReviewStatus.PENDING,
        version=0,
        reasons=["A cybersecurity request was classified as out of scope."],
        query="Analyze CVE-2099-99999",
        route=Route.CAG_RAG_TOOL,
        draft=GeneratedAnswer(summary="Incorrect scope.", out_of_scope=True),
        evidence=[],
        incident=None,
        reflection=ReflectionReport(
            completeness_score=1.0,
            context_used=[],
            missing_sources=[],
            unsupported_claims=0,
            gaps=[],
        ),
        warnings=[],
        revision_count=0,
        feedback_history=[],
    ).model_dump(mode="json")


def test_pending_review_is_not_an_autonomous_pass() -> None:
    review = pending_review()
    assert "metadata" not in review
    assert "answer" not in review
    assert "claims" not in review
    for expectation in ("graph", "missing", "scope"):
        assert not CHECK(review, expectation, "test-model")
        summary = SUMMARIZE(review, 202, expectation, "test-model")
        assert summary["passed"] is False
        assert summary["human_review_required"] is True
        assert summary["status"] == "pending"
        assert summary["reasons"] == review["reasons"]
        assert summary["run_id"] == review["run_id"]
        assert summary["kg_citations"] is None
        assert summary["fallback"] is None


def test_checker_rejects_inconsistent_analysis_response_shapes() -> None:
    with pytest.raises(ValueError, match="pending review"):
        SUMMARIZE({"status": "pending", "run_id": "review-123"}, 202, "missing", "test-model")
    with pytest.raises(ValueError, match="Unexpected analysis response"):
        SUMMARIZE(pending_review(), 200, "missing", "test-model")


def test_checker_reports_three_of_four_and_never_decides_review(
    tmp_path, monkeypatch, capsys
) -> None:
    def sourced(run_id: str) -> dict:
        report = result(
            out_of_scope=False,
            assessment="A quoted cybersecurity fact.",
            claims=[{"status": "supported_fact"}],
        )
        report["run_id"] = run_id
        report["metadata"]["knowledge_graph"] = {
            "attempted": True,
            "available": True,
            "cited_evidence_ids": ["ev-12345678"],
        }
        report["reflection"] = {"factual_validation_failures": 0}
        return report

    scope = result(
        out_of_scope=True, assessment="VERA answers only cybersecurity questions."
    )
    scope["run_id"] = "scope-run"
    request = httpx.Request("POST", "http://127.0.0.1:8000/v1/analyze")
    payloads = [
        httpx.Response(200, json=sourced("powershell-run"), request=request),
        httpx.Response(200, json=sourced("weakness-run"), request=request),
        httpx.Response(202, json=pending_review(), request=request),
        httpx.Response(200, json=scope, request=request),
    ]
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "http://127.0.0.1:8000"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, path, **kwargs):
            calls.append(path)
            return payloads.pop(0)

    monkeypatch.setitem(
        MAIN.__globals__, "Settings",
        lambda: SimpleNamespace(llm_provider="openai", llm_model="test-model"),
    )
    monkeypatch.setitem(MAIN.__globals__, "httpx", SimpleNamespace(Client=Client))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="Human review required for review-123"):
        MAIN()

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["passed"] for line in lines[:4]] == [True, True, False, True]
    assert lines[2]["http_status"] == 202
    assert lines[2]["human_review_required"] is True
    assert lines[-1] == {"passed": 3, "total": 4, "pending_reviews": 1}
    reports = json.loads((tmp_path / ".vera/local-model-checks.json").read_text())
    assert reports[2]["result"] == pending_review()
    assert reports[2]["reasons"] == pending_review()["reasons"]
    assert reports[2]["status"] == "pending"
    assert calls == ["/v1/analyze"] * 4
