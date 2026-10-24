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
                "social": "Ciao! Sono VERA: posso aiutarti con domande di cybersecurity.",
                "out_of_scope": (
                    "Questo argomento esula dalla mia specializzazione. "
                    "Posso aiutarti con la cybersecurity."
                ),
                "clarification": "Mi dai qualche dettaglio in più su ciò che vuoi sapere?",
            }
            return GeneratedAnswer(
                summary=messages[plan.intent], claims=[],
                out_of_scope=plan.intent == "out_of_scope",
            )
        return compose_deterministic(request, route, evidence, alerts, statistics)
