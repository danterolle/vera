from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.plans import ResourcePlan
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
        *,
        plan: ResourcePlan | None = None,
    ) -> GeneratedAnswer:
        if plan and plan.intent != "cybersecurity":
            messages = {
                "social": "Hello! I'm VERA. I can help with cybersecurity questions.",
                "out_of_scope": (
                    "That topic is outside my specialization. "
                    "I can help with cybersecurity."
                ),
                "clarification": (
                    "Could you provide a little more detail about what you'd like to know?"
                ),
            }
            return GeneratedAnswer(
                summary=messages[plan.intent], claims=[],
                out_of_scope=plan.intent == "out_of_scope",
            )
        return compose_deterministic(request, route, evidence, alerts, statistics)
