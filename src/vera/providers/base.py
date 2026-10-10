from typing import Protocol

from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest


class ModelProvider(Protocol):
    name: str
    external: bool

    def classify(self, query: str) -> Route: ...

    def generate(
        self,
        request: AnalysisRequest,
        route: Route,
        evidence: list[Evidence],
        alerts: list[DetectionAlert],
        statistics: StreamStatistics,
        feedback: list[str],
    ) -> GeneratedAnswer: ...
