from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.composers import compose_deterministic


class DeterministicProvider:
    name = "deterministic"
    external = False

    def classify(self, query: str) -> Route:
        return Route.CAG_RAG

    def generate(
        self,
        request: AnalysisRequest,
        route: Route,
        evidence: list[Evidence],
        alerts: list[DetectionAlert],
        statistics: StreamStatistics,
        feedback: list[str],
    ) -> GeneratedAnswer:
        return compose_deterministic(request, route, evidence, alerts, statistics)
