from dataclasses import dataclass, field
from typing import Protocol

import httpx

from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence, make_evidence


class SourceAdapter(Protocol):
    source: SourceType
    url: str

    def lookup(self, cve_id: str) -> Evidence: ...


@dataclass(frozen=True)
class SourceLookup:
    evidence: list[Evidence]
    tool_calls: int
    warnings: list[str] = field(default_factory=list)


def unavailable_evidence(
    source: SourceType,
    cve_id: str,
    detail: str,
    url: str,
) -> Evidence:
    return make_evidence(
        source,
        f"{cve_id} - {source.value} unavailable",
        detail,
        url=url,
        status=EvidenceStatus.UNAVAILABLE,
        metadata={"cve_id": cve_id},
    )


def get_json(response: httpx.Response, source: SourceType) -> dict:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"{source.value} returned a non-object JSON response")
    return payload
