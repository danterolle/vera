from vera.domain.enums import ClaimStatus


def expanded_summary(scenario) -> str:
    """Teach source-backed detail, not invented examples or unsupported mechanics."""
    identifiers = {
        identifier
        for claim in scenario.claims if claim.status == ClaimStatus.SUPPORTED_FACT
        for identifier in claim.evidence_ids
    }
    passages = [scenario.summary]
    seen = set()
    for item in scenario.evidence:
        if item.id in identifiers and item.content not in seen:
            passages.append(f"Documented evidence ({item.title}):\n{item.content}")
            seen.add(item.content)
    return "\n\n".join(passages)
