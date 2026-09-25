from vera.domain.enums import ClaimStatus, SourceType
from vera.domain.evidence import Citation, Claim, make_evidence
from vera.reasoning.reflection import reflect


def test_non_factual_validation_error_does_not_reduce_grounding_count() -> None:
    evidence = make_evidence(SourceType.NVD, "Record", "Supported content")
    claim = Claim(
        text=evidence.content,
        status=ClaimStatus.SUPPORTED_FACT,
        evidence_ids=[evidence.id],
        citations=[
            Citation(
                evidence_id=evidence.id,
                supporting_quote=evidence.content,
            )
        ],
    )
    report = reflect(
        [claim],
        [evidence],
        ["Claim 1 (unavailable): unavailable claim references available evidence"],
    )
    assert report.validation_failures == 1
    assert report.factual_validation_failures == 0
    assert report.grounding_failures == 0
