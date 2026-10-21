from vera.domain.enums import ClaimStatus, Severity, SourceType
from vera.domain.evidence import Claim, make_evidence
from vera.domain.reports import DetectionAlert, GeneratedAnswer, ReflectionReport
from vera.domain.requests import AnalysisRequest
from vera.reasoning.review import review_reasons


def state(query: str, *, out_of_scope: bool = False) -> dict:
    return {
        "request": AnalysisRequest(query=query),
        "alerts": [],
        "evidence": [
            make_evidence(SourceType.CAG, "Least privilege", "Limit account permissions.")
        ],
        "draft": GeneratedAnswer(
            summary="Assessment",
            claims=[Claim(text="Limit account permissions.", status=ClaimStatus.SUPPORTED_FACT)],
            out_of_scope=out_of_scope,
        ),
        "reflection": ReflectionReport(
            completeness_score=1,
            context_used=["cag"],
            missing_sources=[],
            unsupported_claims=0,
            gaps=[],
        ),
    }


def test_supported_question_and_unrelated_scope_finish_automatically() -> None:
    assert review_reasons(state("What is least privilege?")) == []
    assert review_reasons(state("How do I bake bread?", out_of_scope=True)) == []


def test_out_of_scope_cve_and_unsupported_claim_require_review() -> None:
    confused = state("Analyze CVE-2099-9999", out_of_scope=True)
    assert "classified as out of scope" in " ".join(review_reasons(confused))
    uncertain = state("What is least privilege?")
    uncertain["reflection"].unsupported_claims = 1
    assert "lack verified support" in " ".join(review_reasons(uncertain))


def test_high_alert_and_missing_identifier_evidence_require_review() -> None:
    request = state("Analyze CVE-2099-9999")
    request["alerts"] = [
        DetectionAlert(
            rule_id="NET-SCAN",
            title="Port scan",
            description="High-risk activity",
            severity=Severity.HIGH,
        )
    ]
    reasons = review_reasons(request)
    assert len(reasons) == 2
    assert any("high or critical" in reason for reason in reasons)
    assert any("CVE-2099-9999" in reason for reason in reasons)


def test_supported_offline_cve_does_not_pause_for_missing_live_source() -> None:
    request = state("Analyze CVE-2021-44228")
    request["evidence"] = [
        make_evidence(
            SourceType.NVD,
            "CVE-2021-44228 - bundled snapshot",
            "A dated source snapshot exists.",
        )
    ]
    request["reflection"].missing_sources = ["cve_org"]
    assert review_reasons(request) == []
