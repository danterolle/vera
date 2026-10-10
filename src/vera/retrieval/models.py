from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence


class CorpusFeed(StrEnum):
    ALL = "all"
    MITRE_ATTACK = "mitre-attack"
    CISA_KEV = "cisa-kev"


class FeedManifest(BaseModel):
    feed: CorpusFeed
    source: SourceType
    source_url: str
    version: str
    documents: int = Field(ge=0)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FeedBatch(BaseModel):
    manifest: FeedManifest
    evidence: list[Evidence]


class CorpusStatus(BaseModel):
    bundled_documents: int
    synchronized_documents: int
    total_documents: int
    by_source: dict[str, int]
    feeds: list[FeedManifest]


class CorpusSyncReport(BaseModel):
    total_documents: int
    feeds: list[FeedManifest]
