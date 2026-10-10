from vera.domain.enums import ClaimStatus, SourceType
from vera.domain.evidence import Claim, make_evidence
from vera.providers.rendering import render_answer


def test_uncited_retrieved_evidence_is_described_accurately() -> None:
    evidence = make_evidence(SourceType.NVD, "Record", "Retrieved evidence")
    claim = Claim(text="Uncited inference", status=ClaimStatus.SYSTEM_INFERENCE)
    rendered = render_answer("Summary", [claim], [evidence], None)
    assert "No evidence was cited in the final claims." in rendered
    assert "No evidence was available." not in rendered
