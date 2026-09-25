from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vera.domain.enums import Route, Severity
from vera.domain.evidence import Claim, Evidence


class DetectionAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    description: str
    severity: Severity
    technique_id: str | None = None
    cve_ids: list[str] = Field(default_factory=list)
    event_indexes: list[int] = Field(default_factory=list)


class StreamStatistics(BaseModel):
    total_events: int = 0
    total_bytes: int = 0
    protocols: dict[str, int] = Field(default_factory=dict)
    source_ips: dict[str, int] = Field(default_factory=dict)
    destination_ports: dict[str, int] = Field(default_factory=dict)


class IncidentReport(BaseModel):
    severity: Severity
    title: str
    summary: str
    alerts: list[DetectionAlert]
    statistics: StreamStatistics
    recommended_actions: list[str]


class GeneratedAnswer(BaseModel):
    summary: str = Field(min_length=1, max_length=12_000)
    claims: list[Claim] = Field(default_factory=list)


class ReflectionReport(BaseModel):
    completeness_score: float = Field(ge=0.0, le=1.0)
    context_used: list[str]
    missing_sources: list[str]
    unsupported_claims: int
    gaps: list[str]


class RunMetrics(BaseModel):
    latency_ms: float = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    retrieved_documents: int = Field(ge=0)
    source_coverage: float = Field(ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    route: Route
    answer: str
    claims: list[Claim]
    evidence: list[Evidence]
    incident: IncidentReport | None = None
    reflection: ReflectionReport
    metrics: RunMetrics
    trace: list[str]
    warnings: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
