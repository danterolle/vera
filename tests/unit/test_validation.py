import pytest

from vera.domain.enums import ClaimStatus, Route, SourceType
from vera.domain.evidence import Citation, Claim, make_evidence
from vera.domain.reports import GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.deterministic import DeterministicProvider
from vera.reasoning.validation import validate_and_repair


def test_unknown_citation_is_reclassified() -> None:
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text="Unsupported statement",
                status=ClaimStatus.SUPPORTED_FACT,
                evidence_ids=["missing"],
            )
        ],
    )
    outcome = validate_and_repair(draft, [], repair=True)
    assert outcome.errors
    assert outcome.draft.claims[0].status == ClaimStatus.SYSTEM_INFERENCE
    assert outcome.draft.claims[0].evidence_ids == []


def test_authoritative_citation_remains_supported() -> None:
    evidence = make_evidence(SourceType.NVD, "Record", "Supported content")
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text="Supported content",
                status=ClaimStatus.SUPPORTED_FACT,
                evidence_ids=[evidence.id],
                citations=[
                    Citation(
                        evidence_id=evidence.id,
                        supporting_quote="Supported content",
                    )
                ],
            )
        ],
    )
    outcome = validate_and_repair(draft, [evidence], repair=True)
    assert not outcome.errors
    assert outcome.draft.claims[0].status == ClaimStatus.SUPPORTED_FACT


def test_unrelated_real_citation_is_rejected() -> None:
    evidence = make_evidence(
        SourceType.NVD,
        "CVE record",
        "Apache Log4j is a Java logging library.",
    )
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text="The Moon is made of cheese.",
                status=ClaimStatus.SUPPORTED_FACT,
                evidence_ids=[evidence.id],
                citations=[
                    Citation(
                        evidence_id=evidence.id,
                        supporting_quote=evidence.content,
                    )
                ],
            )
        ],
    )
    outcome = validate_and_repair(draft, [evidence], repair=True)
    assert outcome.errors
    assert "not grounded" in outcome.errors[0]
    assert outcome.draft.claims[0].status == ClaimStatus.SYSTEM_INFERENCE


@pytest.mark.parametrize(
    ("claim_text", "evidence_text"),
    [
        ("The CVSS score is 9.8.", "The CVSS score is 10.0."),
        ("Log4j is not vulnerable.", "Log4j is vulnerable."),
        ("The exploitation probability is 50%.", "The exploitation probability is 50."),
        ("The CVSS score is greater than 9.0.", "The CVSS score is less than 9.0."),
        (
            "The CVSS score is 9.8 and EPSS probability is 0.2.",
            "The CVSS score is 0.2 and EPSS probability is 9.8.",
        ),
    ],
)
def test_numeric_and_negation_contradictions_are_rejected(
    claim_text: str,
    evidence_text: str,
) -> None:
    evidence = make_evidence(SourceType.NVD, "Record", evidence_text)
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text=claim_text,
                status=ClaimStatus.SUPPORTED_FACT,
                evidence_ids=[evidence.id],
                citations=[
                    Citation(
                        evidence_id=evidence.id,
                        supporting_quote=evidence.content,
                    )
                ],
            )
        ],
    )
    outcome = validate_and_repair(draft, [evidence], repair=True)
    assert outcome.errors
    assert outcome.draft.claims[0].status == ClaimStatus.SYSTEM_INFERENCE


def test_explicit_absence_can_be_reported_without_a_source() -> None:
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text="No relevant evidence was available.",
                status=ClaimStatus.UNAVAILABLE,
            )
        ],
    )
    outcome = validate_and_repair(draft, [], repair=False)
    assert outcome.errors == []


def test_all_secondary_citations_must_be_valid() -> None:
    primary = make_evidence(SourceType.NVD, "Primary", "Log4j is a logging library.")
    secondary = make_evidence(SourceType.CVE_ORG, "Secondary", "A second source.")
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text=primary.content,
                status=ClaimStatus.SUPPORTED_FACT,
                evidence_ids=[primary.id, secondary.id],
                citations=[
                    Citation(evidence_id=primary.id, supporting_quote=primary.content),
                    Citation(evidence_id=secondary.id, supporting_quote="Fabricated quote"),
                ],
            )
        ],
    )
    outcome = validate_and_repair(draft, [primary, secondary], repair=False)
    assert outcome.errors
    assert "not present verbatim" in outcome.errors[0]


def test_repair_removes_citation_missing_from_evidence_ids() -> None:
    evidence = make_evidence(SourceType.NVD, "Record", "Supported content.")
    draft = GeneratedAnswer(
        summary="Summary",
        claims=[
            Claim(
                text=evidence.content,
                status=ClaimStatus.SUPPORTED_FACT,
                citations=[
                    Citation(
                        evidence_id=evidence.id,
                        supporting_quote=evidence.content,
                    )
                ],
            )
        ],
    )
    outcome = validate_and_repair(draft, [evidence], repair=True)
    assert outcome.errors
    assert outcome.draft.claims[0].evidence_ids == []
    assert outcome.draft.claims[0].citations == []


def test_deterministic_provider_bounds_long_evidence_claim() -> None:
    evidence = make_evidence(SourceType.MITRE_ATTACK, "Long record", "x" * 5000)
    draft = DeterministicProvider().generate(
        AnalysisRequest(query="Explain the record"),
        Route.CAG_RAG,
        [evidence],
        [],
        StreamStatistics(),
        [],
    )
    assert len(draft.claims[0].text) == 4000
    assert draft.claims[0].evidence_ids == [evidence.id]
    assert draft.claims[0].citations[0].supporting_quote == "x" * 4000
