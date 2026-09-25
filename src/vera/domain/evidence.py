from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=8, max_length=64)
    source: SourceType
    title: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    content: str = Field(min_length=1, max_length=12_000)
    status: EvidenceStatus = EvidenceStatus.AVAILABLE
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    status: ClaimStatus
    evidence_ids: list[str] = Field(default_factory=list)


def make_evidence(
    source: SourceType,
    title: str,
    content: str,
    *,
    url: str | None = None,
    status: EvidenceStatus = EvidenceStatus.AVAILABLE,
    metadata: dict[str, Any] | None = None,
) -> Evidence:
    fingerprint = sha256(f"{source}:{title}:{content}".encode()).hexdigest()[:16]
    return Evidence(
        id=f"ev-{fingerprint}",
        source=source,
        title=title,
        content=content,
        url=url,
        status=status,
        metadata=metadata or {},
    )
