from pathlib import Path
from runpy import run_path

CHECK = run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/check-local-model.py"),
    run_name="local_model_checks",
)["check"]


def result(*, out_of_scope: bool, assessment: str, claims: list[dict] | None = None) -> dict:
    return {
        "metadata": {"model": "test-model", "provider_fallback": False,
                     "out_of_scope": out_of_scope},
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
