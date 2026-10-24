from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.reports import GeneratedAnswer, IncidentReport, ReflectionReport, RunMetrics


class ReviewStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "revise"]
    version: int = Field(ge=0)
    decision_id: UUID
    feedback: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_feedback(self) -> "ReviewDecision":
        if self.feedback is not None:
            self.feedback = self.feedback.strip()
        if self.action in {"reject", "revise"} and not self.feedback:
            raise ValueError("Rejecting or revising a draft requires feedback")
        return self


class ReviewRecord(BaseModel):
    run_id: str
    status: ReviewStatus
    version: int = Field(ge=0)
    reasons: list[str]
    query: str
    route: Route
    draft: GeneratedAnswer
    evidence: list[Evidence]
    incident: IncidentReport | None
    reflection: ReflectionReport
    warnings: list[str]
    revision_count: int = Field(ge=0)
    can_revise: bool = False
    feedback_history: list[str]
    error: str | None = None
    retry_decision: ReviewDecision | None = None
    metadata: dict = Field(default_factory=dict)
    metrics: RunMetrics | None = None
    session_id: str | None = None
    created_at: str | None = None
