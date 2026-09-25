from vera.domain.enums import ClaimStatus, Route, SourceType
from vera.domain.evidence import Claim, make_evidence
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
                text="Supported statement",
                status=ClaimStatus.SUPPORTED_FACT,
                evidence_ids=[evidence.id],
            )
        ],
    )
    outcome = validate_and_repair(draft, [evidence], repair=True)
    assert not outcome.errors
    assert outcome.draft.claims[0].status == ClaimStatus.SUPPORTED_FACT


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
