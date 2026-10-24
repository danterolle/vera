from typing import TypedDict

from vera.domain.actions import ReActAction, ReActObservation
from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import (
    AnalysisResult,
    DetectionAlert,
    GeneratedAnswer,
    IncidentReport,
    ReflectionReport,
    StreamStatistics,
)
from vera.domain.requests import AnalysisRequest


class GraphState(TypedDict, total=False):
    request: AnalysisRequest
    request_received_at: str
    run_id: str
    started_at: float
    active_ms: float
    route: Route
    route_reason: str
    resource_plan: ResourcePlan
    evidence: list[Evidence]
    memory: list[Evidence]
    alerts: list[DetectionAlert]
    statistics: StreamStatistics
    incident: IncidentReport | None
    draft: GeneratedAnswer
    reflection: ReflectionReport
    result: AnalysisResult
    generation_attempts: int
    validation_errors: list[str]
    retry_generation: bool
    provider_fallback: bool
    model_calls: int
    tool_calls: int
    react_action: ReActAction
    react_steps: int
    react_searches: list[str]
    react_lookups: list[str]
    react_observations: list[ReActObservation]
    trace: list[str]
    warnings: list[str]
    knowledge_graph: dict
    review_required: bool
    review_reasons: list[str]
    review_action: str
    review_feedback: str
    revision_count: int
    revision_error: str | None
