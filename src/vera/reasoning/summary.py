import re
from collections.abc import Sequence

from vera.domain.enums import ClaimStatus
from vera.domain.evidence import Claim


def summary_review_errors(summary: str, claims: Sequence[Claim]) -> list[str]:
    """Only extractive factual prose can be checked without a semantic reviewer."""
    remaining = summary.strip()
    facts = sorted(
        (claim.text for claim in claims if claim.status == ClaimStatus.SUPPORTED_FACT),
        key=len,
        reverse=True,
    )
    for text in facts:
        remaining = remaining.replace(text, "")
    if not re.search(r"\w", remaining):
        return []
    return [
        "Summary contains non-extractive prose requiring human verification of "
        "correctness, relevance, completeness and uncertainty."
    ]
